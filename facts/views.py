from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.reconciliation import get_or_create_asset
from facts.approval import stage_governed_changes
from facts.dynamic_fields import sync_dynamic_fields
from facts.models import ApprovalFieldConfig, HostFact
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

        fixed_values = {
            "os_family": ansible_facts.get("ansible_distribution", ""),
            "os_version": ansible_facts.get("ansible_distribution_version", ""),
            "source_platform": hypervisor.get("source_platform"),
            "vm_uuid": hypervisor.get("vm_uuid"),
            "cluster_name": hypervisor.get("cluster_name"),
            "power_state": hypervisor.get("power_state"),
            "num_cpu": hypervisor.get("num_cpu"),
            "memory_mb": hypervisor.get("memory_mb"),
        }
        raw_facts = {"ansible_facts": ansible_facts, "hypervisor": hypervisor}

        with transaction.atomic():
            asset = get_or_create_asset(hostname, primary_ip=primary_ip)
            existing_host_fact = HostFact.objects.filter(asset=asset).first()

            if existing_host_fact is None:
                # 신규 자산: 승인 없이 즉시 반영
                new_host_fact = HostFact.objects.create(asset=asset, raw_facts=raw_facts, **fixed_values)
                sync_dynamic_fields(new_host_fact)
            else:
                governed_fixed_keys = set(
                    ApprovalFieldConfig.objects.filter(
                        source_type=ApprovalFieldConfig.SourceType.FIXED
                    ).values_list("key", flat=True)
                )
                governed_dynamic_keys = set(
                    ApprovalFieldConfig.objects.filter(
                        source_type=ApprovalFieldConfig.SourceType.DYNAMIC
                    ).values_list("key", flat=True)
                )

                for key, value in fixed_values.items():
                    if key not in governed_fixed_keys:
                        setattr(existing_host_fact, key, value)
                existing_host_fact.raw_facts = raw_facts
                existing_host_fact.save()

                sync_dynamic_fields(existing_host_fact, exclude_keys=governed_dynamic_keys)
                stage_governed_changes(existing_host_fact, ansible_facts, hypervisor)

        return Response(
            {"asset_id": asset.id, "hostname": asset.hostname, "updated": True},
            status=status.HTTP_201_CREATED,
        )
