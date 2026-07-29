from rest_framework import serializers

from was.models import WasConfigSource


class WasConfigIngestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=WasConfigSource.Kind.choices)
    content = serializers.CharField()
