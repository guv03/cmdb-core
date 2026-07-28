from django.contrib import admin

from processes.matching import resync_definition
from processes.models import ApplicationDefinition, DetectedApplication, ProcessSnapshot


@admin.register(ApplicationDefinition)
class ApplicationDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "match_pattern", "is_active"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # 정의를 등록/수정한 즉시 기존 스냅샷에도 소급 반영 - push를 기다릴 필요 없게
        resync_definition(obj)


@admin.register(ProcessSnapshot)
class ProcessSnapshotAdmin(admin.ModelAdmin):
    list_display = ["asset", "collected_at"]
    search_fields = ["asset__hostname"]


@admin.register(DetectedApplication)
class DetectedApplicationAdmin(admin.ModelAdmin):
    list_display = ["snapshot", "definition", "matched_line"]
    list_filter = ["definition"]
    search_fields = ["snapshot__asset__hostname", "definition__name"]
