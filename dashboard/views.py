import json
import subprocess
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from core.models import Asset, Service
from dashboard.excel_import import (
    ImportFileError,
    apply_updates,
    export_manual_field_workbook,
    parse_manual_field_workbook,
)
from dashboard.list_export import (
    export_apache_vhost_workbook,
    export_change_history_workbook,
    export_db_config_history_workbook,
    export_db_instance_workbook,
    export_jeus_container_workbook,
    export_nginx_vhost_workbook,
    export_process_workbook,
    export_was_config_workbook,
    export_was_history_workbook,
    export_webconfig_history_workbook,
    export_webconfig_workbook,
    export_webtob_vhost_workbook,
)
from dashboard.queries import (
    WAS_KIND_LABELS,
    WEB_KIND_LABELS,
    build_db_config_rows,
    build_jeus_container_rows,
    build_rows,
    build_sort_columns,
    build_system_host_rows,
    build_system_host_vm_entries,
    build_webtob_vhost_rows,
    describe_overview_filter,
    get_apache_vhost_queryset,
    get_asset_queryset,
    get_change_history_queryset,
    get_dashboard_columns,
    get_db_config_dynamic_field_definitions,
    get_db_config_history_queryset,
    get_db_config_queryset,
    get_db_instance_queryset,
    get_dynamic_field_definitions,
    get_jeus_container_queryset,
    get_nginx_vhost_queryset,
    get_os_overview_data,
    get_os_version_breakdown,
    get_process_queryset,
    get_service_container_queryset,
    get_system_host_dynamic_field_definitions,
    get_system_host_queryset,
    get_system_hosts_for_vms,
    get_was_config_queryset,
    get_was_history_queryset,
    get_was_overview_data,
    get_was_version_breakdown,
    get_web_overview_data,
    get_web_service_queryset,
    get_web_version_breakdown,
    get_webconfig_history_queryset,
    get_webconfig_queryset,
    get_webtob_vhost_queryset,
)
from dashboard.topology import build_service_topology_graph, render_topology_svg
from dashboard.serializers import AssetSerializer
from database.excel_import import (
    ImportFileError as DbImportFileError,
    apply_updates as apply_db_config_updates,
    export_db_config_workbook,
    parse_db_config_workbook,
)
from database.models import DbConfigSource, DbConfigSourceFieldDefinition, DbConfigSourceFieldValue
from facts.dynamic_fields import coerce_fact_value, is_valid_choice
from facts.models import FactFieldDefinition, HostFactValue
from processes.models import ProcessSnapshot
from webconfig.diff import unified_diff_lines
from webconfig.excel_import import (
    VHOST_MODELS,
    ImportFileError as ServiceImportFileError,
    apply_service_updates,
    export_service_workbook,
    parse_service_workbook,
)
from systems.dynamic_fields import is_valid_choice as system_is_valid_choice
from systems.excel_import import (
    ImportFileError as SystemImportFileError,
    apply_updates as apply_system_host_updates,
    export_system_host_workbook,
    parse_system_host_workbook,
)
from systems.models import SystemHost, SystemHostFieldDefinition, SystemHostFieldValue, SystemSource
from systems.sync import get_or_create_physical_source, sync_physical_host_asset
from was.linkage import apply_container_service, apply_vhost_service
from was.models import JeusContainer, WasConfigSource
from webconfig.models import WebConfigSource, WebServiceDomain, WebtobVhost


def _resolve_service(name: str) -> Service | None:
    """서비스명 인라인 편집 입력을 core.Service로 변환 - 같은 이름이면 기존 Service를
    재사용하고(get_or_create), 빈 문자열이면 연결 해제(None)."""
    name = (name or "").strip()
    if not name:
        return None
    service, _ = Service.objects.get_or_create(name=name)
    return service


class DashboardLoginView(LoginView):
    template_name = "dashboard/login.html"


class OverviewView(LoginRequiredMixin, TemplateView):
    """상단 "CMDB" 로고를 누르면 오는 통합대시보드 홈 - OS/WEB/WAS 섹션을 카테고리별 개수
    타일로 한눈에 보여준다. sections를 리스트로 둬서 나중에 섹션이 더 늘어나도(예: 서비스
    조회) 여기 한 줄만 추가하면 되고 템플릿/JS는 그대로 재사용된다."""

    template_name = "dashboard/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sections"] = [
            {"key": "os", "title": "OS", **get_os_overview_data()},
            {"key": "web", "title": "WEB", **get_web_overview_data()},
            {"key": "was", "title": "WAS", **get_was_overview_data()},
        ]
        return context


class OverviewDrilldownView(LoginRequiredMixin, View):
    """통합대시보드의 카테고리 타일 클릭 시 그 아래 도넛으로 펼쳐 보여줄 하위 분포(AJAX).
    section으로 어느 축(OS/WEB/WAS)인지 고르고 key로 그 축 안의 카테고리를 지정한다."""

    BREAKDOWN_FUNCS = {
        "os": get_os_version_breakdown,
        "web": get_web_version_breakdown,
        "was": get_was_version_breakdown,
    }

    def get(self, request):
        section = request.GET.get("section", "")
        key = request.GET.get("key", "")
        breakdown_func = self.BREAKDOWN_FUNCS.get(section)
        if breakdown_func is None or not key:
            return JsonResponse({"error": "section/key 파라미터가 올바르지 않습니다."}, status=400)
        return JsonResponse({"section": section, "key": key, "items": breakdown_func(key)})


class AssetListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/asset_list.html"
    context_object_name = "assets"
    paginate_by = 50

    def get_queryset(self):
        return get_asset_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dynamic_field_definitions = list(get_dynamic_field_definitions())
        context["columns"] = get_dashboard_columns(self.request)
        context["rows"] = build_rows(context["assets"], dynamic_field_definitions)
        context["current_q"] = self.request.GET.get("q", "")
        context["overview_filter"] = describe_overview_filter(
            self.request, ("os_family", "OS"), ("os_version", "버전")
        )
        return context


class AssetDetailView(LoginRequiredMixin, DetailView):
    """자산 목록 행 클릭 시 모달로 뜨는 상세 - 메인 테이블과 같은 build_rows()를 재사용해서
    같은 컬럼(동적 필드 포함)을 가로 스크롤 대신 세로 label-value 표로 보여준다. 컬럼이
    admin에서 늘어나도 이 화면은 코드 수정 없이 그대로 따라간다(메인 테이블과 동일한 원리).
    편집은 여기서 하지 않음 - MANUAL 필드 편집 모달을 이 모달 위에 또 띄우면 중첩 모달이
    되고, 이 화면에 뜨는 모달 위에 또 모달을 띄우는 대신 prompt()를 쓰는 기존 관례로는
    checkbox/select/date 타입까지 있는 MANUAL 필드를 제대로 못 다뤄서 read-only로 유지."""

    template_name = "dashboard/asset_detail.html"
    context_object_name = "asset"

    def get_queryset(self):
        return Asset.objects.select_related("hostfact").prefetch_related(
            Prefetch("hostfact__values", queryset=HostFactValue.objects.select_related("field_definition"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dynamic_field_definitions = list(get_dynamic_field_definitions())
        context["row"] = build_rows([self.object], dynamic_field_definitions)[0]
        hostfact = getattr(self.object, "hostfact", None)
        raw_facts = hostfact.raw_facts if hostfact is not None else {}
        context["raw_facts_json"] = json.dumps(raw_facts, indent=2, ensure_ascii=False)

        # "연결된 시스템"은 VM 자신의 하드웨어 정보가 아니라 시스템 목록에 이미 선언된 컬럼
        # (고정 이름/종류/VM 수 + admin이 등록한 동적 필드)을 그대로 보여준다 - 자산관리
        # 관점에서 "이 OS가 어느 물리 시스템에 있나"를 보려는 목적이라 시스템 쪽 정보는
        # 시스템 쪽 정의를 그대로 따라간다(build_system_host_vm_entries와 대칭).
        linked_vms = list(self.object.system_vms.select_related("host__source"))
        system_dynamic_field_definitions = list(get_system_host_dynamic_field_definitions())
        linked_hosts = get_system_hosts_for_vms(linked_vms)
        context["linked_system_host_rows"] = build_system_host_rows(
            linked_hosts, system_dynamic_field_definitions
        )
        return context


class SystemHostManualFieldUpdateView(LoginRequiredMixin, View):
    """"시스템" 목록의 인라인 편집(셀 하나 클릭 → 그 필드 값만 저장)용 엔드포인트 -
    AssetManualFieldUpdateView와 동일 패턴, SystemHostFieldDefinition/Value 기준.

    kind=physical 호스트는 AUTO 필드도 받아준다 - build_system_host_rows의 is_manual 판정과
    맞춰야 목록에서 클릭 가능하게 보여준 셀이 실제로도 저장돼야 하므로. vCenter/Nutanix
    호스트는 지금처럼 MANUAL만 허용(AUTO를 여기로 고쳐봐야 다음 push의 sync_host_fields가
    조용히 덮어써서 혼란만 생김)."""

    def post(self, request, pk):
        host = get_object_or_404(SystemHost.objects.select_related("source"), pk=pk)
        is_physical = host.source.kind == SystemSource.Kind.PHYSICAL

        field_definition = SystemHostFieldDefinition.objects.filter(
            pk=request.POST.get("field_id"), is_visible=True
        ).first()
        if field_definition is None:
            return JsonResponse({"error": "필드를 찾을 수 없습니다."}, status=404)
        if field_definition.source != SystemHostFieldDefinition.Source.MANUAL and not is_physical:
            return JsonResponse({"error": "자동 추출 필드는 직접 수정할 수 없습니다."}, status=400)

        if field_definition.value_type == SystemHostFieldDefinition.ValueType.BOOL:
            raw_value = request.POST.get("value") == "true"
        else:
            raw_value = request.POST.get("value", "").strip() or None

        if not system_is_valid_choice(field_definition, raw_value):
            return JsonResponse({"error": "허용되지 않은 값입니다."}, status=400)

        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        parse_failed = (
            field_definition.value_type
            in (SystemHostFieldDefinition.ValueType.NUMBER, SystemHostFieldDefinition.ValueType.DATE)
            and raw_value is not None
            and all(v is None for v in defaults.values())
        )
        if parse_failed:
            return JsonResponse({"error": "값 형식이 올바르지 않습니다."}, status=400)

        SystemHostFieldValue.objects.update_or_create(
            host=host, field_definition=field_definition, defaults=defaults
        )

        display_value = next(
            (v for v in (defaults["value_text"], defaults["value_number"], defaults["value_date"]) if v is not None),
            "",
        )
        return JsonResponse({"value": str(display_value)})


class SystemHostManualCreateView(LoginRequiredMixin, View):
    """"시스템" 목록의 "물리 장비 등록" 모달 - vCenter/Nutanix push 경로 없이 사람이 직접
    SystemHost(kind=physical)를 만든다. 소스 이름은 사용자가 직접 입력(전산실/그룹별로
    나눠 관리 가능 - vCenter/Nutanix가 이미 (kind, name)으로 인스턴스를 구분하는 것과 동일
    패턴). external_id는 vCenter moref 같은 자연 키가 없어 UUID를 발급(사용자에게 안 보임)."""

    def post(self, request):
        name = (request.POST.get("name") or "").strip()
        source_name = (request.POST.get("source_name") or "").strip()
        if not name:
            return JsonResponse({"error": "이름을 입력하세요."}, status=400)
        if not source_name:
            return JsonResponse({"error": "소스를 입력하세요."}, status=400)

        host = SystemHost.objects.create(
            source=get_or_create_physical_source(source_name),
            external_id=uuid.uuid4().hex,
            name=name,
        )
        sync_physical_host_asset(host, request.POST.get("hostname") or "")
        return JsonResponse({"id": host.pk})


class SystemHostManualUpdateView(LoginRequiredMixin, View):
    """물리 장비 이름/소스/연결 자산 수정 - kind=physical인 SystemHost만 대상으로 잠근다
    (vCenter/Nutanix가 보고한 host는 push로만 바뀌어야 하므로 이 경로로 못 건드리게). 소스를
    바꾸면(다른 그룹으로 이동) 같은 이름의 physical 소스가 없으면 새로 만든다."""

    def post(self, request, pk):
        host = get_object_or_404(
            SystemHost.objects.select_related("source"),
            pk=pk,
            source__kind=SystemSource.Kind.PHYSICAL,
        )
        name = (request.POST.get("name") or "").strip()
        source_name = (request.POST.get("source_name") or "").strip()
        if not name:
            return JsonResponse({"error": "이름을 입력하세요."}, status=400)
        if not source_name:
            return JsonResponse({"error": "소스를 입력하세요."}, status=400)

        host.name = name
        host.source = get_or_create_physical_source(source_name)
        host.save(update_fields=["name", "source"])
        sync_physical_host_asset(host, request.POST.get("hostname") or "")
        return JsonResponse({"id": host.pk})


class SystemHostManualDeleteView(LoginRequiredMixin, View):
    """물리 장비 삭제 - kind=physical만 대상(CASCADE로 딸린 SystemVm/필드값도 함께 정리).
    push 기반 정리가 없는 kind라 폐기 시 사람이 직접 지워야 한다."""

    def post(self, request, pk):
        host = get_object_or_404(SystemHost, pk=pk, source__kind=SystemSource.Kind.PHYSICAL)
        host.delete()
        return JsonResponse({"deleted": True})


class AssetManualFieldUpdateView(LoginRequiredMixin, View):
    """자산 목록의 인라인 편집(셀 하나 클릭 → 그 필드 값만 저장)용 엔드포인트. JSON으로 응답한다."""

    def post(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk)
        hostfact = getattr(asset, "hostfact", None)
        if hostfact is None:
            return JsonResponse({"error": "아직 수집된 facts가 없어 저장할 수 없습니다."}, status=400)

        field_definition = FactFieldDefinition.objects.filter(
            pk=request.POST.get("field_id"),
            source=FactFieldDefinition.Source.MANUAL,
            is_visible=True,
        ).first()
        if field_definition is None:
            return JsonResponse({"error": "수기 입력 필드를 찾을 수 없습니다."}, status=404)

        if field_definition.value_type == FactFieldDefinition.ValueType.BOOL:
            raw_value = request.POST.get("value") == "true"
        else:
            raw_value = request.POST.get("value", "").strip() or None

        if not is_valid_choice(field_definition, raw_value):
            return JsonResponse({"error": "허용되지 않은 값입니다."}, status=400)

        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        parse_failed = (
            field_definition.value_type
            in (FactFieldDefinition.ValueType.NUMBER, FactFieldDefinition.ValueType.DATE)
            and raw_value is not None
            and all(v is None for v in defaults.values())
        )
        if parse_failed:
            return JsonResponse({"error": "값 형식이 올바르지 않습니다."}, status=400)

        HostFactValue.objects.update_or_create(
            host_fact=hostfact, field_definition=field_definition, defaults=defaults
        )
        asset.last_changed_at = timezone.now()
        asset.save(update_fields=["last_changed_at"])

        display_value = next(
            (v for v in (defaults["value_text"], defaults["value_number"], defaults["value_date"]) if v is not None),
            "",
        )
        return JsonResponse({"value": str(display_value)})


class AssetExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_manual_field_workbook()


class ManualFieldImportView(LoginRequiredMixin, View):
    template_name = "dashboard/manual_field_import.html"

    def _manual_field_labels(self):
        return list(
            FactFieldDefinition.objects.filter(
                source=FactFieldDefinition.Source.MANUAL, is_visible=True
            ).values_list("label", flat=True)
        )

    def get(self, request):
        return render(request, self.template_name, {"manual_field_labels": self._manual_field_labels()})

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        context = {"manual_field_labels": self._manual_field_labels()}

        if not uploaded_file:
            messages.error(request, "업로드할 엑셀 파일을 선택해주세요.")
            return render(request, self.template_name, context)

        try:
            result = parse_manual_field_workbook(uploaded_file)
        except ImportFileError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, context)

        payload = [
            {"asset_id": u.asset_id, "field_id": u.field_id, "new_value": u.new_value}
            for u in result.updates
        ]
        context.update({"result": result, "payload_json": json.dumps(payload)})
        return render(request, self.template_name, context)


class ManualFieldImportConfirmView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.POST.get("payload", "[]"))
        except json.JSONDecodeError:
            payload = []

        applied, asset_count = apply_updates(payload)
        if applied:
            messages.success(request, f"{asset_count}개 자산에 수기 필드 값 {applied}건을 반영했습니다.")
        else:
            messages.warning(request, "반영할 내용이 없습니다.")

        return redirect("dashboard-asset-list")


class AssetListAPIView(ListAPIView):
    serializer_class = AssetSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_asset_queryset(self.request)


class ChangeHistoryListView(LoginRequiredMixin, ListView):
    """webconfig/was의 *HistoryListView와 동일한 취지 - 승인/반려 없는 읽기 전용 이력."""

    template_name = "dashboard/change_history.html"
    context_object_name = "changes"
    paginate_by = 50

    def get_queryset(self):
        return get_change_history_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_q"] = self.request.GET.get("q", "")
        context["columns"] = build_sort_columns(
            self.request, ["asset", "detected_at"], default="-detected_at"
        )
        return context


class ChangeHistoryExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_change_history_workbook()


class WebConfigListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/webconfig_list.html"
    context_object_name = "sources"
    paginate_by = 50

    def get_queryset(self):
        return get_webconfig_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(
            self.request,
            [
                "hostname",
                "ip",
                "kind",
                "solution_version",
                "solution_fix",
                "vhost_count",
                "last_changed_at",
                "last_pushed_at",
            ],
            default="hostname",
        )
        context["overview_filter"] = describe_overview_filter(
            self.request,
            ("kind", "종류", lambda v: WEB_KIND_LABELS.get(v, v)),
            ("solution_version", "버전"),
        )
        return context


class WebConfigExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_webconfig_workbook()


class WebConfigDetailView(LoginRequiredMixin, DetailView):
    template_name = "dashboard/webconfig_detail.html"
    context_object_name = "source"

    def get_queryset(self):
        return WebConfigSource.objects.select_related("asset", "node").prefetch_related(
            "vhosts__ssl",
            "vhosts__service",
            "vhosts__svrgroups__servers",
            "vhosts__uris__server",
            "apache_vhosts__service",
            "nginx_vhosts__service",
        )


class WebConfigHistoryListView(LoginRequiredMixin, ListView):
    """웹설정 원본이 실제로 바뀐 시점만 남기는 읽기 전용 이력 - 승인/반려 없음(push는 그대로 즉시 반영)."""

    template_name = "dashboard/webconfig_history.html"
    context_object_name = "revisions"
    paginate_by = 20

    def get_queryset(self):
        return get_webconfig_history_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for revision in context["revisions"]:
            revision.diff_lines = unified_diff_lines(revision.old_content, revision.new_content)
        context["current_q"] = self.request.GET.get("q", "")
        return context


class WebConfigHistoryExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_webconfig_history_workbook()


class WebtobVhostListView(LoginRequiredMixin, ListView):
    """웹 설정 목록(서버 단위)과 달리 vhost 하나 = 행 하나로 여러 서버를 가로질러 본다.
    WebToB 전용 화면(SvrGroup/URI 등 WebToB 개념이라 kind 공통 화면으로는 안 만듦)."""

    template_name = "dashboard/webtob_vhost_list.html"
    context_object_name = "vhosts"
    paginate_by = 50

    def get_queryset(self):
        return get_webtob_vhost_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rows"] = build_webtob_vhost_rows(context["vhosts"])
        context["columns"] = build_sort_columns(
            self.request,
            [
                "hostname",
                "ip",
                "vhost_name",
                "domain",
                "hostalias",
                "port",
                "docroot",
                "limit_request_body",
                "ssl_flag",
                "ssl_protocols",
                "logging",
                "errorlog",
                "service_name",
            ],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class WebtobVhostExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_webtob_vhost_workbook()


class ApacheVhostListView(LoginRequiredMixin, ListView):
    """WebtobVhostListView와 같은 취지의 Apache 전용 목록 - SvrGroup/URI 개념이 없어
    build_webtob_vhost_rows 같은 요약 단계 없이 vhost를 그대로 렌더링한다."""

    template_name = "dashboard/apache_vhost_list.html"
    context_object_name = "vhosts"
    paginate_by = 50

    def get_queryset(self):
        return get_apache_vhost_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(
            self.request,
            ["hostname", "ip", "domain", "hostalias", "port", "docroot", "ssl_flag", "ssl_protocols", "logging", "errorlog", "service_name"],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class ApacheVhostExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_apache_vhost_workbook()


class NginxVhostListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/nginx_vhost_list.html"
    context_object_name = "vhosts"
    paginate_by = 50

    def get_queryset(self):
        return get_nginx_vhost_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(
            self.request,
            ["hostname", "ip", "domain", "hostalias", "port", "docroot", "ssl_flag", "ssl_protocols", "logging", "errorlog", "service_name"],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class NginxVhostExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_nginx_vhost_workbook()


class WasConfigListView(LoginRequiredMixin, ListView):
    """WAS 버전의 WebConfigListView - 서버(자산+kind) 단위 목록. asset은 admin 호스트를
    가리키고, container_count는 이 소스에 딸린 컨테이너 전체 수(각 컨테이너가 다른 자산에
    속하더라도 소스 자체의 속성이라 그대로 카운트)."""

    template_name = "dashboard/was_list.html"
    context_object_name = "sources"
    paginate_by = 50

    def get_queryset(self):
        return get_was_config_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(
            self.request,
            [
                "hostname",
                "ip",
                "kind",
                "instance_name",
                "solution_version",
                "container_count",
                "last_changed_at",
                "last_pushed_at",
            ],
            default="hostname",
        )
        context["overview_filter"] = describe_overview_filter(
            self.request,
            ("kind", "종류", lambda v: WAS_KIND_LABELS.get(v, v)),
            ("solution_version", "버전"),
        )
        return context


class WasConfigExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_was_config_workbook()


class WasConfigDetailView(LoginRequiredMixin, DetailView):
    template_name = "dashboard/was_detail.html"
    context_object_name = "source"

    def get_queryset(self):
        return WasConfigSource.objects.select_related("asset").prefetch_related(
            "containers__asset",
            "containers__service",
            "containers__webtob_connectors__webtob_server__source__asset",
            "containers__data_sources__db_instance__source",
        )


class WasConfigHistoryListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/was_history.html"
    context_object_name = "revisions"
    paginate_by = 20

    def get_queryset(self):
        return get_was_history_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for revision in context["revisions"]:
            revision.diff_lines = unified_diff_lines(revision.old_content, revision.new_content)
        context["current_q"] = self.request.GET.get("q", "")
        return context


class WasConfigHistoryExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_was_history_workbook()


class JeusContainerListView(LoginRequiredMixin, ListView):
    """WebtobVhostListView와 같은 취지의 JEUS 전용 목록 - 다만 Hostname 컬럼은
    container.asset(컨테이너 자신의 node-name으로 해석된 자산)을 쓴다. source.asset(=push를
    보낸 admin 호스트)과 다를 수 있어서 소스 쪽 hostname을 쓰면 틀린 정보가 된다."""

    template_name = "dashboard/jeus_container_list.html"
    context_object_name = "containers"
    paginate_by = 50

    def get_queryset(self):
        return get_jeus_container_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rows"] = build_jeus_container_rows(context["containers"])
        context["columns"] = build_sort_columns(
            self.request,
            [
                "hostname",
                "ip",
                "instance_name",
                "node_name",
                "container",
                "listen_port",
                "ssl_port",
                "service_name",
            ],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class JeusContainerExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_jeus_container_workbook()


class DbConfigListView(LoginRequiredMixin, ListView):
    """DB(Standalone/RAC) 목록 - DbConfigSource 하나 = 행 하나. systems의 SystemListView와
    같은 구조(고정 컬럼 + admin 등록 동적 필드)를 그대로 따른다 - 클러스터/버전 등 실측
    스키마가 확실하지 않은 값은 처음부터 동적 필드로 시작."""

    template_name = "dashboard/db_config_list.html"
    context_object_name = "sources"
    paginate_by = 50

    def get_queryset(self):
        return get_db_config_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dynamic_field_definitions = list(get_db_config_dynamic_field_definitions())
        context["rows"] = build_db_config_rows(context["sources"], dynamic_field_definitions)
        context["columns"] = build_sort_columns(
            self.request,
            ["db_unique_name", "kind", "db_name", "database_role", "open_mode", "hostname", "instance_count",
             "last_changed_at", "last_pushed_at"],
            default="db_unique_name",
        )
        context["current_q"] = self.request.GET.get("q", "")
        # MANUAL 셀 편집 모달의 선택형(choice) 입력 구성용 - 시스템 목록과 동일 패턴.
        context["field_choices_json"] = [
            {
                "field_id": fd.id,
                "choices": (
                    [c.value for c in fd.choices.all()]
                    if fd.value_type == DbConfigSourceFieldDefinition.ValueType.CHOICE
                    else None
                ),
            }
            for fd in dynamic_field_definitions
        ]
        return context


class DbConfigExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_db_config_workbook()


class DbConfigImportView(LoginRequiredMixin, View):
    """DB 목록 MANUAL 필드 엑셀 업로드 - SystemHostImportView와 동일 패턴, 매칭 키만
    db_unique_name(단일 컬럼 - Asset.hostname과 같은 이유로 이미 전역 유일)."""

    template_name = "dashboard/db_config_import.html"

    def _manual_field_labels(self):
        return list(
            DbConfigSourceFieldDefinition.objects.filter(
                source=DbConfigSourceFieldDefinition.Source.MANUAL, is_visible=True
            ).values_list("label", flat=True)
        )

    def get(self, request):
        return render(request, self.template_name, {"manual_field_labels": self._manual_field_labels()})

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        context = {"manual_field_labels": self._manual_field_labels()}

        if not uploaded_file:
            messages.error(request, "업로드할 엑셀 파일을 선택해주세요.")
            return render(request, self.template_name, context)

        try:
            result = parse_db_config_workbook(uploaded_file)
        except DbImportFileError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, context)

        payload = [
            {"source_id": u.source_id, "field_id": u.field_id, "new_value": u.new_value}
            for u in result.updates
        ]
        context.update({"result": result, "payload_json": json.dumps(payload)})
        return render(request, self.template_name, context)


class DbConfigImportConfirmView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.POST.get("payload", "[]"))
        except json.JSONDecodeError:
            payload = []

        applied, source_count = apply_db_config_updates(payload)
        if applied:
            messages.success(request, f"{source_count}개 DB에 수기 필드 값 {applied}건을 반영했습니다.")
        else:
            messages.warning(request, "반영할 내용이 없습니다.")

        return redirect("dashboard-db-config-list")


class DbConfigManualFieldUpdateView(LoginRequiredMixin, View):
    """"DB" 목록의 인라인 편집(셀 하나 클릭 → 그 필드 값만 저장)용 엔드포인트 -
    SystemHostManualFieldUpdateView와 동일 패턴(kind=physical 같은 예외는 없음 - DB는
    항상 push로만 생성됨)."""

    def post(self, request, pk):
        source = get_object_or_404(DbConfigSource, pk=pk)

        field_definition = DbConfigSourceFieldDefinition.objects.filter(
            pk=request.POST.get("field_id"),
            source=DbConfigSourceFieldDefinition.Source.MANUAL,
            is_visible=True,
        ).first()
        if field_definition is None:
            return JsonResponse({"error": "수기 입력 필드를 찾을 수 없습니다."}, status=404)

        if field_definition.value_type == DbConfigSourceFieldDefinition.ValueType.BOOL:
            raw_value = request.POST.get("value") == "true"
        else:
            raw_value = request.POST.get("value", "").strip() or None

        if not is_valid_choice(field_definition, raw_value):
            return JsonResponse({"error": "허용되지 않은 값입니다."}, status=400)

        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        parse_failed = (
            field_definition.value_type
            in (DbConfigSourceFieldDefinition.ValueType.NUMBER, DbConfigSourceFieldDefinition.ValueType.DATE)
            and raw_value is not None
            and all(v is None for v in defaults.values())
        )
        if parse_failed:
            return JsonResponse({"error": "값 형식이 올바르지 않습니다."}, status=400)

        DbConfigSourceFieldValue.objects.update_or_create(
            source=source, field_definition=field_definition, defaults=defaults
        )

        display_value = next(
            (v for v in (defaults["value_text"], defaults["value_number"], defaults["value_date"]) if v is not None),
            "",
        )
        return JsonResponse({"value": str(display_value)})


class DbConfigDetailView(LoginRequiredMixin, DetailView):
    """DB 상세 - 인스턴스별 카드로 보여준다(WasConfigDetailView와 같은 구조)."""

    template_name = "dashboard/db_config_detail.html"
    context_object_name = "source"

    def get_queryset(self):
        return DbConfigSource.objects.select_related("asset").prefetch_related("instances__asset")


class DbConfigHistoryListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/db_config_history.html"
    context_object_name = "revisions"
    paginate_by = 20

    def get_queryset(self):
        return get_db_config_history_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for revision in context["revisions"]:
            revision.diff_lines = unified_diff_lines(revision.old_content, revision.new_content)
        context["current_q"] = self.request.GET.get("q", "")
        return context


class DbConfigHistoryExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_db_config_history_workbook()


class DbInstanceListView(LoginRequiredMixin, ListView):
    """DB를 가로질러 인스턴스 단위로 검색·정렬하는 전용 목록 - JeusContainerListView와
    같은 취지(RAC 노드별로 한 행씩 나옴)."""

    template_name = "dashboard/db_instance_list.html"
    context_object_name = "instances"
    paginate_by = 50

    def get_queryset(self):
        return get_db_instance_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(
            self.request,
            ["db_unique_name", "hostname", "ip", "instance_name", "instance_number", "status", "version",
             "listener_port"],
            default="instance_name",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class DbInstanceExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_db_instance_workbook()


class SystemListView(LoginRequiredMixin, ListView):
    """진짜 물리 장비(ESXi 호스트/AHV 노드) 목록 - SystemHost 하나 = 행 하나. 그 위에 떠있는
    VM(OS)들은 여기서 안 보여주고 상세 화면에서 관계형으로 나열한다(호스트:VM = 1:N)."""

    template_name = "dashboard/system_list.html"
    context_object_name = "hosts"
    paginate_by = 50

    def get_queryset(self):
        return get_system_host_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dynamic_field_definitions = list(get_system_host_dynamic_field_definitions())
        context["rows"] = build_system_host_rows(context["hosts"], dynamic_field_definitions)
        context["columns"] = build_sort_columns(
            self.request,
            ["source_name", "name", "kind", "vm_count"],
            default="name",
        )
        # MANUAL 셀 편집 모달의 선택형(choice) 입력 구성용 - 자산 목록의
        # {{ columns|json_script }} 패턴과 같은 이유(JS에서 field_id별 선택지 조회).
        context["field_choices_json"] = [
            {
                "field_id": fd.id,
                "choices": (
                    [c.value for c in fd.choices.all()]
                    if fd.value_type == SystemHostFieldDefinition.ValueType.CHOICE
                    else None
                ),
            }
            for fd in dynamic_field_definitions
        ]
        # "물리 장비 등록/편집" 모달의 자산 연결 입력용 - 서비스 구성도 화면의 <input list>
        # datalist와 같은 패턴(별도 자동완성 라이브러리 없이 네이티브 datalist로 해결).
        context["asset_hostnames"] = list(
            Asset.objects.order_by("hostname").values_list("hostname", flat=True)
        )
        # 소스 입력 datalist용 - 이미 쓰인 physical 소스 이름을 보여줘서 그룹 재사용을 유도.
        context["physical_source_names"] = list(
            SystemSource.objects.filter(kind=SystemSource.Kind.PHYSICAL)
            .order_by("name")
            .values_list("name", flat=True)
        )
        # "물리 장비 등록" 모달을 열 때 소스 입력란에 채워둘 기본값 - 처음 쓰는 사람은 그룹을
        # 나눌 생각이 없을 수 있어 아무것도 안 입력해도 되게, 기존에 쓰인 이름이 있으면 그걸,
        # 없으면(첫 등록) "수기 등록"을 기본으로 제안한다.
        context["default_physical_source_name"] = (
            context["physical_source_names"][0] if context["physical_source_names"] else "수기 등록"
        )
        return context


class SystemDetailView(LoginRequiredMixin, DetailView):
    """물리 호스트 상세 - 자기 하드웨어 스펙 + 그 위에 떠있는 VM(OS) 목록을 관계형으로
    보여준다(asset이 매칭된 VM은 자산 상세로 링크)."""

    template_name = "dashboard/system_detail.html"
    context_object_name = "host"

    def get_queryset(self):
        # vm.asset 자체(hostfact 등)는 여기서 안 쓴다 - build_system_host_vm_entries가
        # 매칭된 자산을 별도로(OS 목록과 같은 select_related/prefetch로) 다시 조회해서
        # OS 쪽 컬럼 값을 만든다. 여기선 vm.asset_id/hostname/name만 있으면 충분.
        return SystemHost.objects.select_related("source").prefetch_related(
            "vms", "field_values__field_definition"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dynamic_field_definitions = list(get_system_host_dynamic_field_definitions())
        context["row"] = build_system_host_rows([self.object], dynamic_field_definitions)[0]

        # "이 장비에 떠있는 OS(VM)" 표는 VM 자신의 하드웨어 정보가 아니라 OS 목록에 이미
        # 선언된 컬럼(고정 Hostname/IP/OS + admin이 등록한 동적 필드)을 그대로 보여준다 -
        # 자산관리 관점에서 "이 시스템에 어떤 OS가 떠있나"를 보려는 목적이라 OS 쪽 정보는
        # OS 쪽 정의를 그대로 따라간다.
        os_dynamic_field_definitions = list(get_dynamic_field_definitions())
        context["os_columns"] = get_dashboard_columns(self.request)
        context["vm_entries"] = build_system_host_vm_entries(
            self.object.vms.all(), os_dynamic_field_definitions
        )

        # SystemHostFieldDefinition의 key/kind_key_overrides는 이 host.extra 안의 dot-path를
        # 가리킨다 - asset_detail.html의 raw_facts_json과 같은 이유로, admin이 새 필드를
        # 등록할 때 실제 원본 구조를 보고 경로를 찾을 수 있어야 한다.
        context["extra_json"] = json.dumps(self.object.extra, indent=2, ensure_ascii=False)
        return context


class SystemHostExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_system_host_workbook()


class SystemHostImportView(LoginRequiredMixin, View):
    """시스템 목록 MANUAL 필드 엑셀 업로드 - dashboard의 ManualFieldImportView와 같은 패턴
    (다운로드→몇 칸만 고침→재업로드), 매칭 키만 source_name+name."""

    template_name = "dashboard/system_host_import.html"

    def _manual_field_labels(self):
        return list(
            SystemHostFieldDefinition.objects.filter(
                source=SystemHostFieldDefinition.Source.MANUAL, is_visible=True
            ).values_list("label", flat=True)
        )

    def get(self, request):
        return render(request, self.template_name, {"manual_field_labels": self._manual_field_labels()})

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        context = {"manual_field_labels": self._manual_field_labels()}

        if not uploaded_file:
            messages.error(request, "업로드할 엑셀 파일을 선택해주세요.")
            return render(request, self.template_name, context)

        try:
            result = parse_system_host_workbook(uploaded_file)
        except SystemImportFileError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, context)

        payload = [
            {"host_id": u.host_id, "field_id": u.field_id, "new_value": u.new_value}
            for u in result.updates
        ]
        context.update({"result": result, "payload_json": json.dumps(payload)})
        return render(request, self.template_name, context)


class SystemHostImportConfirmView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.POST.get("payload", "[]"))
        except json.JSONDecodeError:
            payload = []

        applied, host_count = apply_system_host_updates(payload)
        if applied:
            messages.success(request, f"{host_count}개 물리 장비에 수기 필드 값 {applied}건을 반영했습니다.")
        else:
            messages.warning(request, "반영할 내용이 없습니다.")

        return redirect("dashboard-system-list")


class ServiceExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_service_workbook()


class ServiceImportView(LoginRequiredMixin, View):
    template_name = "dashboard/service_import.html"

    def get(self, request):
        return render(request, self.template_name, {})

    def post(self, request):
        uploaded_file = request.FILES.get("file")

        if not uploaded_file:
            messages.error(request, "업로드할 엑셀 파일을 선택해주세요.")
            return render(request, self.template_name, {})

        try:
            result = parse_service_workbook(uploaded_file)
        except ServiceImportFileError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {})

        payload = [
            {"kind": "service_name", "service_domain_id": u.service_domain_id, "new_value": u.new_value}
            for u in result.service_name_updates
        ]
        context = {
            "result": result,
            "payload_json": json.dumps(payload),
            "total_count": len(result.service_name_updates),
        }
        return render(request, self.template_name, context)


class ServiceImportConfirmView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            payload = json.loads(request.POST.get("payload", "[]"))
        except json.JSONDecodeError:
            payload = []

        applied, asset_count = apply_service_updates(payload)
        if applied:
            messages.success(request, f"{asset_count}개 자산에 값 {applied}건을 반영했습니다.")
        else:
            messages.warning(request, "반영할 내용이 없습니다.")

        return redirect("dashboard-webservice-list")


class WebServiceListView(LoginRequiredMixin, ListView):
    """WEB(도메인 기준, WebServiceDomain)과 WAS(컨테이너 기준, JeusContainer)를 한 화면에
    나란히 보여준다 - 서비스 배정을 여기서만 편집하고(vhost/컨테이너 목록 화면은 읽기 전용)
    한곳에서 WEB/WAS 전체 서비스 현황을 확인할 수 있게. WAS 표는 검색만 WEB과 공유하고
    (같은 q) 별도 정렬/페이지네이션은 두지 않는다(get_service_container_queryset 참고)."""

    template_name = "dashboard/webservice_list.html"
    context_object_name = "service_domains"
    paginate_by = 50

    def get_queryset(self):
        return get_web_service_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(
            self.request, ["service_name", "domain", "port", "hostname", "kind"], default="domain"
        )
        context["was_rows"] = get_service_container_queryset(self.request)
        return context


class WebServiceDomainServiceUpdateView(LoginRequiredMixin, View):
    """서비스 조회 화면(WEB 표)에서의 서비스명 인라인 편집. 원본은 kind별 vhost 쪽
    (VHOST_MODELS로 kind->모델 매핑)이라 거기에 먼저 반영하고, 같은 vhost가 걸친 나머지
    도메인 행도 함께 맞춘다(도메인별로 서비스명이 갈리면 안 되므로 vhost 단위로 동기화).
    WebToB는 JeusWebtobConnector로 실제 연결된 JeusContainer가 있으면 같은 서비스로 함께
    맞춘다(was.linkage.apply_vhost_service) - 연결된 쪽에 이미 다른 서비스가 있으면 저장
    전에 충돌 정보만 돌려주고, force=1로 재요청하면 그대로 덮어쓴다. Apache/Nginx는 아직
    이런 구조적 연결이 없어 자기 자신만 반영한다."""

    def post(self, request, pk):
        service_domain = get_object_or_404(WebServiceDomain, pk=pk)
        service = _resolve_service(request.POST.get("service_name", ""))
        force = request.POST.get("force") == "1"

        if service_domain.source.kind == WebConfigSource.Kind.WEBTOB:
            vhost = WebtobVhost.objects.filter(
                source=service_domain.source, name=service_domain.vhost_name
            ).first()
            if vhost is not None:
                result = apply_vhost_service(vhost, service, force=force)
                if result["conflict"]:
                    return JsonResponse(
                        {
                            "conflict": True,
                            "peer_labels": result["peer_labels"],
                            "message": "연결된 WAS 컨테이너가 이미 다른 서비스명을 갖고 있습니다: "
                            + ", ".join(result["peer_labels"]),
                        }
                    )
        else:
            model = VHOST_MODELS.get(service_domain.source.kind)
            if model is not None:
                model.objects.filter(
                    source=service_domain.source, name=service_domain.vhost_name
                ).update(service=service)

        service_name = service.name if service else ""
        WebServiceDomain.objects.filter(
            source=service_domain.source, vhost_name=service_domain.vhost_name
        ).update(service_name=service_name)

        return JsonResponse({"service_name": service_name})


class ServiceContainerUpdateView(LoginRequiredMixin, View):
    """서비스 탭(WAS 표)에서의 서비스명 인라인 편집 - WebServiceDomainServiceUpdateView의
    반대 방향(was.linkage.apply_container_service). 연결된 WebtobVhost가 이미 다른
    서비스명을 갖고 있으면 저장 전에 충돌 정보만 돌려주고, force=1로 재요청하면 덮어쓴다."""

    def post(self, request, pk):
        container = get_object_or_404(JeusContainer, pk=pk)
        service = _resolve_service(request.POST.get("service_name", ""))
        force = request.POST.get("force") == "1"

        result = apply_container_service(container, service, force=force)
        if result["conflict"]:
            return JsonResponse(
                {
                    "conflict": True,
                    "peer_labels": result["peer_labels"],
                    "message": "연결된 WEB vhost가 이미 다른 서비스명을 갖고 있습니다: "
                    + ", ".join(result["peer_labels"]),
                }
            )

        return JsonResponse({"service_name": service.name if service else ""})


class ServiceTopologyView(LoginRequiredMixin, TemplateView):
    """서비스 하나를 골라 WEB<->WAS<->시스템 연결을 Graphviz로 그린 구성도. 서비스 탭 행의
    "구성도" 링크(?name=서비스명)로 바로 들어오거나, 이 화면 자체의 검색(datalist)으로
    고를 수도 있다. 표/레인 방식은 OS 이중화 시 같은 서버가 레인마다 반복 표시돼 헷갈리는
    문제가 있어(dashboard/topology.py 모듈 docstring 참고) 실제 그래프+Graphviz 렌더링으로
    바꿨다."""

    template_name = "dashboard/service_topology.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        name = self.request.GET.get("name", "").strip()
        context["service_names"] = Service.objects.order_by("name").values_list("name", flat=True)
        context["current_name"] = name

        if name:
            service = Service.objects.filter(name=name).first()
            if service is None:
                context["not_found"] = True
            else:
                context["service"] = service
                graph = build_service_topology_graph(service)
                if graph["nodes"]:
                    try:
                        context["topology_svg"] = render_topology_svg(graph)
                    except (RuntimeError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
                        context["render_error"] = str(exc)
        return context


class ProcessListView(LoginRequiredMixin, ListView):
    """자산별 ps -ef 스냅샷과 감지된 어플리케이션 - 승인 없이 push 즉시 반영, 이력 없이
    최신 스냅샷만 유지(processes 앱, webconfig와 같은 취지로 facts EAV 구조와 분리)."""

    template_name = "dashboard/process_list.html"
    context_object_name = "snapshots"
    paginate_by = 50

    def get_queryset(self):
        return get_process_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["columns"] = build_sort_columns(self.request, ["hostname", "collected_at"], default="hostname")
        return context


class ProcessExportView(LoginRequiredMixin, View):
    def get(self, request):
        return export_process_workbook()


class ProcessDetailView(LoginRequiredMixin, DetailView):
    template_name = "dashboard/process_detail.html"
    context_object_name = "snapshot"

    def get_queryset(self):
        return ProcessSnapshot.objects.select_related("asset").prefetch_related(
            "detected_applications__definition"
        )
