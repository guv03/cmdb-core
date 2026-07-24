import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from core.models import Asset
from dashboard.excel_import import ImportFileError, apply_updates, parse_manual_field_workbook
from dashboard.queries import (
    build_rows,
    get_asset_queryset,
    get_change_history_queryset,
    get_dashboard_columns,
    get_dynamic_field_definitions,
)
from dashboard.serializers import AssetSerializer
from facts.approval import apply_pending_change, reject_pending_change
from facts.dynamic_fields import coerce_fact_value, is_valid_choice
from facts.models import FactFieldDefinition, HostFactValue, PendingChange


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
