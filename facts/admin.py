from django import forms
from django.contrib import admin

from facts.approval import FIXED_FIELD_PATHS, apply_pending_change, reject_pending_change
from facts.dynamic_fields import backfill_field
from facts.models import (
    FactFieldChoice,
    FactFieldDefinition,
    HostFact,
    HostFactValue,
    PendingChange,
)


@admin.register(HostFact)
class HostFactAdmin(admin.ModelAdmin):
    list_display = [
        "asset",
        "os_family",
        "source_platform",
        "cluster_name",
        "power_state",
        "last_seen_at",
    ]
    list_filter = ["source_platform", "os_family"]
    search_fields = ["asset__hostname", "cluster_name", "vm_uuid"]


class FactFieldChoiceInline(admin.TabularInline):
    model = FactFieldChoice
    extra = 1
    verbose_name = "선택지 (value_type이 '선택형'일 때만 사용)"
    verbose_name_plural = "선택지 (value_type이 '선택형'일 때만 사용)"


class FactFieldDefinitionForm(forms.ModelForm):
    class Meta:
        model = FactFieldDefinition
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source")
        key = cleaned.get("key")

        if source == FactFieldDefinition.Source.FIXED and key not in FIXED_FIELD_PATHS:
            raise forms.ValidationError(
                f"FIXED 필드는 다음 중 하나여야 함: {', '.join(FIXED_FIELD_PATHS)}"
            )
        if source == FactFieldDefinition.Source.MANUAL and cleaned.get("requires_approval"):
            raise forms.ValidationError(
                "MANUAL 필드는 대시보드 입력이 항상 즉시 반영되므로 승인 대상으로 지정할 수 없음"
            )

        return cleaned


@admin.register(FactFieldDefinition)
class FactFieldDefinitionAdmin(admin.ModelAdmin):
    form = FactFieldDefinitionForm
    list_display = [
        "label",
        "key",
        "source",
        "value_type",
        "is_visible",
        "is_searchable",
        "sort_order",
        "requires_approval",
    ]
    list_editable = ["is_visible", "is_searchable", "sort_order", "requires_approval"]
    list_filter = ["source", "value_type", "requires_approval"]
    search_fields = ["key", "label"]
    actions = ["run_backfill"]
    inlines = [FactFieldChoiceInline]

    @admin.action(description="선택한 필드 소급 백필 실행 (AUTO 필드만 대상)")
    def run_backfill(self, request, queryset):
        for field_definition in queryset:
            if field_definition.source != FactFieldDefinition.Source.AUTO:
                self.message_user(
                    request,
                    f"'{field_definition.label}'은 raw facts에서 추출하는 필드가 아니라 백필 대상이 아닙니다.",
                    level="warning",
                )
                continue
            updated = backfill_field(field_definition)
            self.message_user(
                request, f"'{field_definition.label}' ({field_definition.key}): {updated}개 호스트 갱신"
            )


@admin.register(HostFactValue)
class HostFactValueAdmin(admin.ModelAdmin):
    list_display = ["host_fact", "field_definition", "value_text", "value_number", "value_date"]
    list_filter = ["field_definition"]
    search_fields = ["host_fact__asset__hostname"]


@admin.register(PendingChange)
class PendingChangeAdmin(admin.ModelAdmin):
    list_display = [
        "asset",
        "field_definition",
        "old_value",
        "new_value",
        "status",
        "created_at",
        "decided_at",
        "decided_by",
    ]
    list_filter = ["status", "field_definition"]
    search_fields = ["asset__hostname"]
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description="선택한 변경 승인")
    def approve_selected(self, request, queryset):
        count = 0
        for pending_change in queryset.filter(status=PendingChange.Status.PENDING):
            apply_pending_change(pending_change, decided_by=request.user.username)
            count += 1
        self.message_user(request, f"{count}건 승인 처리했습니다.")

    @admin.action(description="선택한 변경 반려")
    def reject_selected(self, request, queryset):
        count = 0
        for pending_change in queryset.filter(status=PendingChange.Status.PENDING):
            reject_pending_change(pending_change, decided_by=request.user.username)
            count += 1
        self.message_user(request, f"{count}건 반려 처리했습니다.")
