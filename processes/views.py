from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.models import Asset
from core.reconciliation import normalize_hostname
from processes.matching import resync_snapshot
from processes.models import ProcessSnapshot
from processes.serializers import ProcessIngestSerializer


class ProcessIngestView(APIView):
    """AWX가 각 서버의 ps -ef 원본을 push하는 엔드포인트. 자산은 hostname으로 찾는다(신규 생성은
    안 함 - 자산 생성은 facts push 경로 하나뿐이라는 원칙 유지)."""

    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProcessIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        hostname = serializer.validated_data["hostname"]
        raw_output = serializer.validated_data["raw_output"]

        asset = Asset.objects.filter(hostname=normalize_hostname(hostname)).first()
        if asset is None:
            return Response(
                {"error": f"등록되지 않은 자산입니다(먼저 facts push로 등록 필요): {hostname}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        snapshot, _ = ProcessSnapshot.objects.update_or_create(
            asset=asset, defaults={"raw_output": raw_output}
        )
        matches = resync_snapshot(snapshot)

        return Response(
            {
                "asset_id": asset.id,
                "hostname": asset.hostname,
                "detected": [match.definition.name for match in matches],
            },
            status=status.HTTP_201_CREATED,
        )
