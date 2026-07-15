from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.reconciliation import get_or_create_asset
from facts.dynamic_fields import sync_dynamic_fields
from facts.models import HostFact
from facts.serializers import FactsIngestSerializer


class FactsIngestView(APIView):
    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FactsIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        hostname = serializer.validated_data["hostname"]
        ansible_facts = serializer.validated_data["ansible_facts"]
        hypervisor = serializer.validated_data["hypervisor"]

        default_ipv4 = ansible_facts.get("ansible_default_ipv4")
        primary_ip = default_ipv4.get("address") if isinstance(default_ipv4, dict) else None

        with transaction.atomic():
            asset = get_or_create_asset(hostname, primary_ip=primary_ip)

            host_fact, _ = HostFact.objects.update_or_create(
                asset=asset,
                defaults={
                    "os_family": ansible_facts.get("ansible_distribution", ""),
                    "os_version": ansible_facts.get("ansible_distribution_version", ""),
                    "source_platform": hypervisor.get("source_platform"),
                    "vm_uuid": hypervisor.get("vm_uuid"),
                    "cluster_name": hypervisor.get("cluster_name"),
                    "power_state": hypervisor.get("power_state"),
                    "num_cpu": hypervisor.get("num_cpu"),
                    "memory_mb": hypervisor.get("memory_mb"),
                    "raw_facts": {"ansible_facts": ansible_facts, "hypervisor": hypervisor},
                },
            )

            sync_dynamic_fields(host_fact)

        return Response(
            {"asset_id": asset.id, "hostname": asset.hostname, "updated": True},
            status=status.HTTP_201_CREATED,
        )
