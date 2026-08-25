from django.contrib import admin

from network.models import NetworkRoute, NetworkRouteBackend


class NetworkRouteBackendInline(admin.TabularInline):
    model = NetworkRouteBackend
    extra = 1
    autocomplete_fields = ["asset"]


@admin.register(NetworkRoute)
class NetworkRouteAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "note"]
    search_fields = ["key", "label", "note"]
    inlines = [NetworkRouteBackendInline]
