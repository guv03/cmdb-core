from rest_framework import serializers


class FactsIngestSerializer(serializers.Serializer):
    hostname = serializers.CharField(max_length=255)
    ansible_facts = serializers.DictField(required=False, default=dict)
    hypervisor = serializers.DictField(required=False, default=dict)
