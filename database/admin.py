from django.contrib import admin

from database.dynamic_fields import backfill_source_field
from database.models import (
    DbConfigSource,
    DbConfigSourceFieldChoice,
    DbConfigSourceFieldDefinition,
    DbConfigSourceRevision,
    DbInstance,
)


class DbInstanceInline(admin.TabularInline):
    model = DbInstance
    extra = 0
    fields = ["instance_name", "instance_number", "host_name", "asset", "status", "version"]


class DbConfigSourceFieldChoiceInline(admin.TabularInline):
    model = DbConfigSourceFieldChoice
    extra = 1
    verbose_name = "선택지 (value_type이 '선택형'일 때만 사용)"
    verbose_name_plural = "선택지 (value_type이 '선택형'일 때만 사용)"


@admin.register(DbConfigSource)
class DbConfigSourceAdmin(admin.ModelAdmin):
    list_display = ["db_unique_name", "kind", "db_name", "database_role", "asset", "last_pushed_at"]
    list_filter = ["kind", "database_role"]
    search_fields = ["db_unique_name", "db_name", "asset__hostname"]
    inlines = [DbInstanceInline]


@admin.register(DbInstance)
class DbInstanceAdmin(admin.ModelAdmin):
    list_display = ["instance_name", "source", "host_name", "asset", "status", "version"]
    list_filter = ["source__kind", "status"]
    search_fields = ["instance_name", "host_name", "asset__hostname"]


@admin.register(DbConfigSourceRevision)
class DbConfigSourceRevisionAdmin(admin.ModelAdmin):
    list_display = ["source", "detected_at"]
    list_filter = ["source__kind"]
    search_fields = ["source__db_unique_name"]
    readonly_fields = ["source", "old_content", "new_content", "detected_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DbConfigSourceFieldDefinition)
class DbConfigSourceFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ["label", "key", "source", "value_type", "is_visible", "sort_order"]
    list_editable = ["is_visible", "sort_order"]
    list_filter = ["source", "value_type"]
    search_fields = ["key", "label"]
    actions = ["run_backfill"]
    inlines = [DbConfigSourceFieldChoiceInline]

    @admin.action(description="선택한 필드 소급 백필 실행 (AUTO 필드만 대상)")
    def run_backfill(self, request, queryset):
        for field_definition in queryset:
            if field_definition.source != DbConfigSourceFieldDefinition.Source.AUTO:
                self.message_user(
                    request,
                    f"'{field_definition.label}'은 extra에서 추출하는 필드가 아니라 백필 대상이 아닙니다.",
                    level="warning",
                )
                continue
            updated = backfill_source_field(field_definition)
            self.message_user(
                request, f"'{field_definition.label}' ({field_definition.key}): {updated}개 DB 갱신"
            )
