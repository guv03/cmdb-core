from django.contrib import admin

from facts.models import FactFieldDefinition, HostFact, HostFactValue


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


@admin.register(FactFieldDefinition)
class FactFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ["label", "key", "value_type", "is_visible", "is_searchable", "sort_order"]
    list_editable = ["is_visible", "is_searchable", "sort_order"]
    search_fields = ["key", "label"]


@admin.register(HostFactValue)
class HostFactValueAdmin(admin.ModelAdmin):
    list_display = ["host_fact", "field_definition", "value_text", "value_number", "value_date"]
    list_filter = ["field_definition"]
    search_fields = ["host_fact__asset__hostname"]
