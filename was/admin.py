from django.contrib import admin

from was.models import (
    JeusWebtobConnector,
    WasConfigSource,
    WasConfigSourceRevision,
    WasContainer,
    WasDataSource,
)


@admin.register(WasConfigSource)
class WasConfigSourceAdmin(admin.ModelAdmin):
    list_display = ["asset", "kind", "instance_name", "solution_version", "config_path", "last_pushed_at"]
    list_filter = ["kind"]
    search_fields = ["asset__hostname", "instance_name"]


@admin.register(WasContainer)
class WasContainerAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "asset", "node_name", "listen_port", "service"]
    list_editable = ["service"]
    search_fields = ["name", "node_name", "service__name", "source__asset__hostname"]


@admin.register(JeusWebtobConnector)
class JeusWebtobConnectorAdmin(admin.ModelAdmin):
    list_display = ["name", "container", "registration_id", "network_address", "port", "webtob_server"]
    search_fields = ["name", "registration_id", "network_address", "container__name"]


@admin.register(WasDataSource)
class WasDataSourceAdmin(admin.ModelAdmin):
    list_display = ["data_source_id", "source", "vendor", "db_host", "port", "database_name", "db_instance"]
    search_fields = ["data_source_id", "db_host", "database_name", "source__asset__hostname"]


@admin.register(WasConfigSourceRevision)
class WasConfigSourceRevisionAdmin(admin.ModelAdmin):
    list_display = ["source", "detected_at"]
    list_filter = ["source__kind"]
    search_fields = ["source__asset__hostname"]
