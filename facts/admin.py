from django import forms
from django.contrib import admin

from facts.dynamic_fields import backfill_field
from facts.models import (
    FactChangeHistory,
    FactFieldChoice,
    FactFieldDefinition,
    HostFact,
    HostFactValue,
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
        overrides = cleaned.get("os_family_key_overrides")

        if overrides:
            if source != FactFieldDefinition.Source.AUTO:
                raise forms.ValidationError("os_family_key_overrides는 AUTO 필드에서만 쓸 수 있음")
            if not isinstance(overrides, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in overrides.items()
            ):
                raise forms.ValidationError(
                    'os_family_key_overrides는 {"os_family 문자열": "경로 문자열"} 형태의 JSON 객체여야 함'
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
    ]
    list_editable = ["is_visible", "is_searchable", "sort_order"]
    list_filter = ["source", "value_type"]
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


@admin.register(FactChangeHistory)
class FactChangeHistoryAdmin(admin.ModelAdmin):
    """읽기 전용 감사 이력 - 승인/반려 절차가 없어졌으므로 승인 액션도 없음(webconfig/was의
    *SourceRevisionAdmin과 동일한 취지)."""

    list_display = ["asset", "field_key", "field_label", "old_value", "new_value", "detected_at"]
    list_filter = ["field_key"]
    search_fields = ["asset__hostname", "field_key", "field_label"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
