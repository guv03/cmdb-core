from django.contrib import admin

from webconfig.models import (
    WebConfigSource,
    WebtobNode,
    WebtobServer,
    WebtobSsl,
    WebtobSvrGroup,
    WebtobUri,
    WebtobVhost,
)


@admin.register(WebConfigSource)
class WebConfigSourceAdmin(admin.ModelAdmin):
    list_display = ["asset", "kind", "last_pushed_at"]
    list_filter = ["kind"]
    search_fields = ["asset__hostname"]


@admin.register(WebtobVhost)
class WebtobVhostAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "hostname", "port", "ssl_flag", "docroot", "service_name"]
    list_editable = ["service_name"]
    list_filter = ["ssl_flag"]
    search_fields = ["name", "hostname", "service_name", "source__asset__hostname"]


@admin.register(WebtobNode)
class WebtobNodeAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "port", "docroot"]
    search_fields = ["name", "source__asset__hostname"]


@admin.register(WebtobSsl)
class WebtobSslAdmin(admin.ModelAdmin):
    list_display = ["name", "source"]
    search_fields = ["name", "source__asset__hostname"]


@admin.register(WebtobSvrGroup)
class WebtobSvrGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "svrtype"]
    search_fields = ["name", "source__asset__hostname"]


@admin.register(WebtobServer)
class WebtobServerAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "svrgroup", "minproc", "maxproc"]
    search_fields = ["name", "source__asset__hostname"]


@admin.register(WebtobUri)
class WebtobUriAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "uri_path", "server"]
    search_fields = ["name", "uri_path", "source__asset__hostname"]
