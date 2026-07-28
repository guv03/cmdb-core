from rest_framework import serializers


class ProcessIngestSerializer(serializers.Serializer):
    hostname = serializers.CharField()
    raw_output = serializers.CharField()
