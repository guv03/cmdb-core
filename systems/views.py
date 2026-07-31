from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from systems.models import SystemSource
from systems.serializers import SystemIngestSerializer
from systems.sync import sync_systems


class SystemIngestView(APIView):
    """AWX가 vCenter/Nutanix Prism Central API를 직접 찔러서 모은 물리 호스트+VM 목록을
    한 번에 push하는 엔드포인트. 개별 호스트 facts push와 완전히 분리된 흐름이다 - 호스트
    하나당 한 번이 아니라 vCenter/Nutanix 인스턴스 하나당 한 번씩(그 안의 물리 호스트/VM
    전체를 배치로) 호출된다. 자산은 hostname 매칭으로만 연결하고 신규 생성은 안 한다(자산
    생성은 facts push 경로 하나뿐이라는 원칙 유지) - 매칭 안 되면 asset=null로 저장하고
    다음 push 때 재해석."""

    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SystemIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kind = serializer.validated_data["kind"]
        source_name = serializer.validated_data["source_name"]
        hosts_payload = serializer.validated_data["hosts"]
        vms_payload = serializer.validated_data["vms"]

        with transaction.atomic():
            source, _ = SystemSource.objects.update_or_create(
                kind=kind, name=source_name, defaults={"raw_response": request.data}
            )
            sync_systems(source, hosts_payload, vms_payload)

        return Response(
            {
                "kind": kind,
                "source_name": source_name,
                "host_count": len(hosts_payload),
                "vm_count": len(vms_payload),
            },
            status=status.HTTP_201_CREATED,
        )
