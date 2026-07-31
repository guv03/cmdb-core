from django.contrib import admin

from was.models import JeusContainer, JeusWebtobConnector, WasConfigSource, WasConfigSourceRevision


@admin.register(WasConfigSource)
class WasConfigSourceAdmin(admin.ModelAdmin):
    list_display = ["asset", "kind", "solution_version", "last_pushed_at"]
    list_filter = ["kind"]
    search_fields = ["asset__hostname"]


@admin.register(JeusContainer)
class JeusContainerAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "asset", "node_name", "listen_port", "service"]
    list_editable = ["service"]
    search_fields = ["name", "node_name", "service__name", "source__asset__hostname"]


@admin.register(JeusWebtobConnector)
class JeusWebtobConnectorAdmin(admin.ModelAdmin):
    list_display = ["name", "container", "registration_id", "network_address", "port", "webtob_server"]
    search_fields = ["name", "registration_id", "network_address", "container__name"]


@admin.register(WasConfigSourceRevision)
class WasConfigSourceRevisionAdmin(admin.ModelAdmin):
    list_display = ["source", "detected_at"]
    list_filter = ["source__kind"]
    search_fields = ["source__asset__hostname"]
