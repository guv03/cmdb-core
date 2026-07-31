from django.contrib import admin

from systems.dynamic_fields import backfill_host_field
from systems.models import (
    SystemDisk,
    SystemHost,
    SystemHostFieldChoice,
    SystemHostFieldDefinition,
    SystemNic,
    SystemSource,
    SystemVm,
)


class SystemDiskInline(admin.TabularInline):
    model = SystemDisk
    extra = 0


class SystemNicInline(admin.TabularInline):
    model = SystemNic
    extra = 0


class SystemHostFieldChoiceInline(admin.TabularInline):
    model = SystemHostFieldChoice
    extra = 1
    verbose_name = "선택지 (value_type이 '선택형'일 때만 사용)"
    verbose_name_plural = "선택지 (value_type이 '선택형'일 때만 사용)"


@admin.register(SystemSource)
class SystemSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "last_pushed_at"]
    list_filter = ["kind"]
    search_fields = ["name"]


@admin.register(SystemHost)
class SystemHostAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "external_id"]
    list_filter = ["source__kind"]
    search_fields = ["name", "external_id"]


@admin.register(SystemVm)
class SystemVmAdmin(admin.ModelAdmin):
    list_display = ["name", "hostname", "asset", "host", "power_state"]
    list_filter = ["host__source__kind", "power_state"]
    search_fields = ["name", "hostname", "asset__hostname", "host__name"]
    inlines = [SystemDiskInline, SystemNicInline]


@admin.register(SystemHostFieldDefinition)
class SystemHostFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ["label", "key", "source", "value_type", "is_visible", "sort_order"]
    list_editable = ["is_visible", "sort_order"]
    list_filter = ["source", "value_type"]
    search_fields = ["key", "label"]
    actions = ["run_backfill"]
    inlines = [SystemHostFieldChoiceInline]

    @admin.action(description="선택한 필드 소급 백필 실행 (AUTO 필드만 대상)")
    def run_backfill(self, request, queryset):
        for field_definition in queryset:
            if field_definition.source != SystemHostFieldDefinition.Source.AUTO:
                self.message_user(
                    request,
                    f"'{field_definition.label}'은 extra에서 추출하는 필드가 아니라 백필 대상이 아닙니다.",
                    level="warning",
                )
                continue
            updated = backfill_host_field(field_definition)
            self.message_user(
                request, f"'{field_definition.label}' ({field_definition.key}): {updated}개 호스트 갱신"
            )
