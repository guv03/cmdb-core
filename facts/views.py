from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.reconciliation import get_or_create_asset
from facts.dynamic_fields import sync_dynamic_fields
from facts.history import compute_fixed_values, record_fact_changes
from facts.models import HostFact
from facts.serializers import FactsIngestSerializer


def _extract_primary_ip(ansible_facts: dict) -> str | None:
    # ansible_facts 딕셔너리 안의 원본 키는 hostvars에 주입될 때 붙는 "ansible_" 접두사가
    # 없다 (예: ansible_facts.distribution, ansible_distribution이 아님).
    default_ipv4 = ansible_facts.get("default_ipv4")
    if isinstance(default_ipv4, dict) and default_ipv4.get("address"):
        return default_ipv4["address"]

    # Windows ansible facts엔 default_ipv4 자체가 없다 - 대신 interfaces 목록에서
    # default_gateway가 걸린(=아웃바운드 기본 경로) 인터페이스의 ipv4.address를 쓴다.
    # 그런 인터페이스가 없으면 첫 interface의 ipv4.address로 폴백.
    interfaces = ansible_facts.get("interfaces")
    if isinstance(interfaces, list):
        candidates = [i for i in interfaces if isinstance(i, dict) and isinstance(i.get("ipv4"), dict)]
        for interface in sorted(candidates, key=lambda i: not i.get("default_gateway")):
            address = interface["ipv4"].get("address")
            if address:
                return address

    return None


class FactsIngestView(APIView):
    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FactsIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        hostname = serializer.validated_data["hostname"]
        ansible_facts = serializer.validated_data["ansible_facts"]
        hypervisor = serializer.validated_data["hypervisor"]

        primary_ip = _extract_primary_ip(ansible_facts)
        raw_facts = {"ansible_facts": ansible_facts, "hypervisor": hypervisor}
        fixed_values = compute_fixed_values(raw_facts)

        with transaction.atomic():
            asset = get_or_create_asset(hostname, primary_ip=primary_ip)
            existing_host_fact = HostFact.objects.filter(asset=asset).first()

            if existing_host_fact is None:
                # 신규 자산: 즉시 반영, 이력 기록 대상 아님(비교할 이전 값 자체가 없음)
                new_host_fact = HostFact.objects.create(asset=asset, raw_facts=raw_facts, **fixed_values)
                sync_dynamic_fields(new_host_fact)
            else:
                # 승인 절차 없음(webconfig/was와 동일) - 값은 무조건 즉시 반영하고, 실제로
                # 바뀐 필드만 조회용 이력(FactChangeHistory)에 남긴다. 값을 덮어쓰기 전에
                # 먼저 비교해야 "이전 값"을 알 수 있다.
                record_fact_changes(existing_host_fact, raw_facts, fixed_values)

                for key, value in fixed_values.items():
                    setattr(existing_host_fact, key, value)
                existing_host_fact.raw_facts = raw_facts
                existing_host_fact.save()

                sync_dynamic_fields(existing_host_fact)

        return Response(
            {"asset_id": asset.id, "hostname": asset.hostname, "updated": True},
            status=status.HTTP_201_CREATED,
        )
