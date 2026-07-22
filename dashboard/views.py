from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from core.models import Asset
from dashboard.queries import (
    build_rows,
    get_asset_queryset,
    get_change_history_queryset,
    get_dashboard_columns,
    get_dynamic_field_definitions,
)
from dashboard.serializers import AssetSerializer
from facts.approval import apply_pending_change, reject_pending_change
from facts.models import PendingChange


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
            messages.success(request, f"'{pending_change.field_config.label}' 변경을 승인했습니다.")
        else:
            reject_pending_change(pending_change, decided_by=request.user.username)
            messages.success(request, f"'{pending_change.field_config.label}' 변경을 반려했습니다.")

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
