import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from core.models import Asset
from dashboard.excel_import import (
    ImportFileError,
    apply_updates,
    export_manual_field_workbook,
    parse_manual_field_workbook,
)
from dashboard.queries import (
    build_jeus_container_rows,
    build_rows,
    build_sort_columns,
    build_webtob_vhost_rows,
    get_apache_vhost_queryset,
    get_asset_queryset,
    get_change_history_queryset,
    get_dashboard_columns,
    get_dynamic_field_definitions,
    get_jeus_container_queryset,
    get_nginx_vhost_queryset,
    get_process_queryset,
    get_was_config_queryset,
    get_was_history_queryset,
    get_web_service_queryset,
    get_webconfig_history_queryset,
    get_webconfig_queryset,
    get_webtob_vhost_queryset,
)
from dashboard.serializers import AssetSerializer
from facts.approval import apply_pending_change, reject_pending_change
from facts.dynamic_fields import coerce_fact_value, is_valid_choice
from facts.models import FactFieldDefinition, HostFactValue, PendingChange
from processes.models import ProcessSnapshot
from webconfig.diff import unified_diff_lines
from webconfig.excel_import import (
    ImportFileError as ServiceImportFileError,
    apply_service_updates,
    export_service_workbook,
    parse_service_workbook,
)
from was.models import JeusContainer, WasConfigSource
from webconfig.models import ApacheVhost, NginxVhost, WebConfigSource, WebServiceDomain, WebtobVhost


class DashboardLoginView(LoginView):
    template_name = "dashboard/login.html"


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
        return context


class AssetFactsDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk)
        hostfact = getattr(asset, "hostfact", None)
        raw_facts = hostfact.raw_facts if hostfact is not None else {}
        return JsonResponse({"hostname": asset.hostname, "raw_facts": raw_facts})


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
    template_name = "dashboard/change_history.html"
    context_object_name = "changes"
    paginate_by = 50

    def get_queryset(self):
        return get_change_history_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_q"] = self.request.GET.get("q", "")
        context["current_status"] = self.request.GET.get("status", "")
        context["status_choices"] = PendingChange.Status.choices
        context["columns"] = build_sort_columns(
            self.request, ["asset", "status", "created_at", "decided_at"], default="-created_at"
        )
        return context


class PendingChangeDecisionView(LoginRequiredMixin, View):
    action = None  # "approve" or "reject"

    def post(self, request, pk):
        pending_change = get_object_or_404(PendingChange, pk=pk, status=PendingChange.Status.PENDING)
        if self.action == "approve":
            apply_pending_change(pending_change, decided_by=request.user.username)
            messages.success(request, f"'{pending_change.field_definition.label}' 변경을 승인했습니다.")
        else:
            reject_pending_change(pending_change, decided_by=request.user.username)
            messages.success(request, f"'{pending_change.field_definition.label}' 변경을 반려했습니다.")

        next_url = request.POST.get("next") or reverse_lazy("dashboard-change-history")
        return redirect(next_url)


class BulkPendingChangeDecisionView(LoginRequiredMixin, View):
    action = None  # "approve" or "reject"

    def post(self, request):
        pks = request.POST.getlist("pk")
        queryset = PendingChange.objects.filter(pk__in=pks, status=PendingChange.Status.PENDING)

        count = 0
        for pending_change in queryset:
            if self.action == "approve":
                apply_pending_change(pending_change, decided_by=request.user.username)
            else:
                reject_pending_change(pending_change, decided_by=request.user.username)
            count += 1

        verb = "승인" if self.action == "approve" else "반려"
        if count:
            messages.success(request, f"{count}건을 일괄 {verb}했습니다.")
        else:
            messages.warning(request, "선택된 대기 건이 없습니다.")

        next_url = request.POST.get("next") or reverse_lazy("dashboard-change-history")
        return redirect(next_url)


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
                "kind",
                "solution_version",
                "solution_fix",
                "vhost_count",
                "last_changed_at",
                "last_pushed_at",
            ],
            default="hostname",
        )
        return context


class WebConfigDetailView(LoginRequiredMixin, DetailView):
    template_name = "dashboard/webconfig_detail.html"
    context_object_name = "source"

    def get_queryset(self):
        return WebConfigSource.objects.select_related("asset", "node").prefetch_related(
            "vhosts__ssl",
            "vhosts__svrgroups__servers",
            "vhosts__uris__server",
            "apache_vhosts",
            "nginx_vhosts",
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
                "vhost_name",
                "domain",
                "hostalias",
                "port",
                "docroot",
                "limit_request_body",
                "ssl_flag",
                "ssl_protocols",
                "ssl_ciphers",
                "logging",
                "errorlog",
                "service_name",
            ],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class WebtobVhostServiceUpdateView(LoginRequiredMixin, View):
    """vhost 카드의 "서비스명" 수기 입력. 승인 절차 없이 즉시 반영(자산 MANUAL 필드와 동일 원칙)."""

    def post(self, request, pk):
        vhost = get_object_or_404(WebtobVhost, pk=pk)
        vhost.service_name = request.POST.get("service_name", "").strip()
        vhost.save(update_fields=["service_name"])
        WebServiceDomain.objects.filter(source=vhost.source, vhost_name=vhost.name).update(
            service_name=vhost.service_name
        )
        return JsonResponse({"service_name": vhost.service_name})


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
            ["hostname", "domain", "hostalias", "port", "docroot", "ssl_flag", "logging", "errorlog", "service_name"],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class ApacheVhostServiceUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        vhost = get_object_or_404(ApacheVhost, pk=pk)
        vhost.service_name = request.POST.get("service_name", "").strip()
        vhost.save(update_fields=["service_name"])
        WebServiceDomain.objects.filter(source=vhost.source, vhost_name=vhost.name).update(
            service_name=vhost.service_name
        )
        return JsonResponse({"service_name": vhost.service_name})


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
            ["hostname", "domain", "hostalias", "port", "docroot", "ssl_flag", "logging", "errorlog", "service_name"],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class NginxVhostServiceUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        vhost = get_object_or_404(NginxVhost, pk=pk)
        vhost.service_name = request.POST.get("service_name", "").strip()
        vhost.save(update_fields=["service_name"])
        WebServiceDomain.objects.filter(source=vhost.source, vhost_name=vhost.name).update(
            service_name=vhost.service_name
        )
        return JsonResponse({"service_name": vhost.service_name})


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
            ["hostname", "kind", "solution_version", "container_count", "last_changed_at", "last_pushed_at"],
            default="hostname",
        )
        return context


class WasConfigDetailView(LoginRequiredMixin, DetailView):
    template_name = "dashboard/was_detail.html"
    context_object_name = "source"

    def get_queryset(self):
        return WasConfigSource.objects.select_related("asset").prefetch_related(
            "containers__asset", "containers__webtob_connectors__webtob_server__source__asset"
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


class JeusContainerListView(LoginRequiredMixin, ListView):
    """WebtobVhostListView와 같은 취지의 JEUS8 전용 목록 - 다만 Hostname 컬럼은
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
            ["hostname", "node_name", "container", "listen_port", "ssl_port", "service_name"],
            default="hostname",
        )
        context["current_q"] = self.request.GET.get("q", "")
        return context


class JeusContainerServiceUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        container = get_object_or_404(JeusContainer, pk=pk)
        container.service_name = request.POST.get("service_name", "").strip()
        container.save(update_fields=["service_name"])
        return JsonResponse({"service_name": container.service_name})


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
        return context


class WebServiceDomainServiceUpdateView(LoginRequiredMixin, View):
    """서비스 조회 화면에서의 서비스명 인라인 편집. 원본은 kind별 vhost 쪽(webtob는 WebtobVhost)
    이라 거기에 먼저 반영하고, 같은 vhost가 걸친 나머지 도메인 행도 함께 맞춘다(도메인별로
    서비스명이 갈리면 안 되므로 vhost 단위로 동기화)."""

    def post(self, request, pk):
        service_domain = get_object_or_404(WebServiceDomain, pk=pk)
        service_name = request.POST.get("service_name", "").strip()

        if service_domain.source.kind == WebConfigSource.Kind.WEBTOB:
            WebtobVhost.objects.filter(
                source=service_domain.source, name=service_domain.vhost_name
            ).update(service_name=service_name)

        WebServiceDomain.objects.filter(
            source=service_domain.source, vhost_name=service_domain.vhost_name
        ).update(service_name=service_name)

        return JsonResponse({"service_name": service_name})


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


class ProcessDetailView(LoginRequiredMixin, DetailView):
    template_name = "dashboard/process_detail.html"
    context_object_name = "snapshot"

    def get_queryset(self):
        return ProcessSnapshot.objects.select_related("asset").prefetch_related(
            "detected_applications__definition"
        )
