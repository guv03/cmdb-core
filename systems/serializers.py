from rest_framework import serializers

from systems.models import SystemSource


class SystemIngestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SystemSource.Kind.choices)
    source_name = serializers.CharField(max_length=255)
    # 항목별 필드는 sync.sync_systems에서 loose하게(.get() 기본값) 처리한다 - facts 앱의
    # ansible_facts/hypervisor DictField와 같은 이유(vCenter/Nutanix 응답 스키마가 버전마다
    # 조금씩 다를 수 있어 엄격한 nested serializer로 고정하면 사소한 차이에도 전체 push가
    # 거부될 위험이 큼).
    hosts = serializers.ListField(child=serializers.DictField(), default=list)
    vms = serializers.ListField(child=serializers.DictField(), default=list)
