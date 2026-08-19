from django.contrib import admin

from network.models import ServiceNetworkBackend, ServiceNetworkMapping


class ServiceNetworkBackendInline(admin.TabularInline):
    model = ServiceNetworkBackend
    extra = 1
    autocomplete_fields = ["asset"]


@admin.register(ServiceNetworkMapping)
class ServiceNetworkMappingAdmin(admin.ModelAdmin):
    list_display = ["service", "external_domain", "external_ip", "internal_vip"]
    search_fields = ["service__name", "external_domain", "external_ip", "internal_vip"]
    autocomplete_fields = ["service"]
    inlines = [ServiceNetworkBackendInline]
