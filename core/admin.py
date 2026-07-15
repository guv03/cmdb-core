from django.contrib import admin

from core.models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["hostname", "primary_ip", "is_active", "created_at", "updated_at"]
    search_fields = ["hostname", "primary_ip"]
    list_filter = ["is_active"]
