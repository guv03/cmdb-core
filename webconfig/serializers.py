from rest_framework import serializers

from webconfig.models import WebConfigSource


class WebConfigIngestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=WebConfigSource.Kind.choices)
    content = serializers.CharField()
