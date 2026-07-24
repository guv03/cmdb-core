from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.models import Asset
from core.reconciliation import normalize_hostname
from webconfig.models import WebConfigSource
from webconfig.parsers import PARSERS
from webconfig.serializers import WebConfigIngestSerializer
from webconfig.sync import sync_webtob

SYNC_FUNCS = {WebConfigSource.Kind.WEBTOB: sync_webtob}


def _extract_hostname(kind: str, sections: dict) -> str | None:
    if kind == WebConfigSource.Kind.WEBTOB:
        node_entries = sections.get("NODE") or {}
        if not node_entries:
            return None
        return next(iter(node_entries.keys()))
    return None


class WebConfigIngestView(APIView):
    """AWX가 웹서버 설정 원본 텍스트를 push하는 엔드포인트. 자산은 *NODE절 이름으로 찾는다
    (신규 생성은 안 함 - 자산 생성은 facts push 경로 하나뿐이라는 원칙 유지)."""

    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WebConfigIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kind = serializer.validated_data["kind"]
        content = serializer.validated_data["content"]

        parser = PARSERS.get(kind)
        if parser is None:
            return Response({"error": f"지원하지 않는 kind: {kind}"}, status=status.HTTP_400_BAD_REQUEST)

        sections = parser(content)
        hostname = _extract_hostname(kind, sections)
        if not hostname:
            return Response(
                {"error": "설정 내용에서 호스트명을 찾지 못했습니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        asset = Asset.objects.filter(hostname=normalize_hostname(hostname)).first()
        if asset is None:
            return Response(
                {"error": f"등록되지 않은 자산입니다(먼저 facts push로 등록 필요): {hostname}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        source, _ = WebConfigSource.objects.update_or_create(
            asset=asset, kind=kind, defaults={"raw_content": content}
        )

        sync_func = SYNC_FUNCS[kind]
        sync_func(source, sections)

        return Response(
            {"asset_id": asset.id, "hostname": asset.hostname, "kind": kind, "updated": True},
            status=status.HTTP_201_CREATED,
        )
