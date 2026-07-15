from rest_framework import serializers

from core.models import Asset
from dashboard.queries import get_dynamic_field_definitions


class AssetSerializer(serializers.ModelSerializer):
    os_family = serializers.CharField(source="hostfact.os_family", default=None)
    cluster_name = serializers.CharField(source="hostfact.cluster_name", default=None)
    power_state = serializers.CharField(source="hostfact.power_state", default=None)
    last_seen_at = serializers.DateTimeField(source="hostfact.last_seen_at", default=None)
    dynamic_fields = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            "id",
            "hostname",
            "primary_ip",
            "os_family",
            "cluster_name",
            "power_state",
            "last_seen_at",
            "dynamic_fields",
        ]

    def get_dynamic_fields(self, asset):
        hostfact = getattr(asset, "hostfact", None)
        if hostfact is None:
            return {}

        values_by_field_id = {
            value.field_definition_id: (
                value.value_text
                if value.value_text is not None
                else value.value_number if value.value_number is not None else value.value_date
            )
            for value in hostfact.values.all()
        }
        return {
            fd.key: values_by_field_id.get(fd.id) for fd in get_dynamic_field_definitions()
        }
