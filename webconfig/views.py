from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.models import Asset
from core.reconciliation import normalize_hostname
from webconfig.models import WebConfigSource, WebConfigSourceRevision
from webconfig.parsers import PARSERS
from webconfig.serializers import WebConfigIngestSerializer
from webconfig.sync import sync_apache, sync_nginx, sync_webtob
from webconfig.version_extract import VERSION_EXTRACTORS

SYNC_FUNCS = {
    WebConfigSource.Kind.WEBTOB: sync_webtob,
    WebConfigSource.Kind.APACHE: sync_apache,
    WebConfigSource.Kind.NGINX: sync_nginx,
}


def _extract_hostname(kind: str, sections: dict, payload_hostname: str) -> str | None:
    if kind == WebConfigSource.Kind.WEBTOB:
        node_entries = sections.get("NODE") or {}
        if not node_entries:
            return None
        return next(iter(node_entries.keys()))
    # apache/nginx는 설정 내용에 서버 자신을 가리키는 절이 없어 AWX가 보낸 hostname을 그대로 쓴다.
    return payload_hostname or None


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
        payload_hostname = serializer.validated_data.get("hostname", "")
        hostname = _extract_hostname(kind, sections, payload_hostname)
        if not hostname:
            message = (
                "설정 내용에서 호스트명을 찾지 못했습니다."
                if kind == WebConfigSource.Kind.WEBTOB
                else "hostname 필드가 없습니다."
            )
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        asset = Asset.objects.filter(hostname=normalize_hostname(hostname)).first()
        if asset is None:
            return Response(
                {"error": f"등록되지 않은 자산입니다(먼저 facts push로 등록 필요): {hostname}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = WebConfigSource.objects.filter(asset=asset, kind=kind).first()
        if existing is not None and existing.raw_content != content:
            WebConfigSourceRevision.objects.create(
                source=existing, old_content=existing.raw_content, new_content=content
            )

        source, _ = WebConfigSource.objects.update_or_create(
            asset=asset, kind=kind, defaults={"raw_content": content}
        )

        version_extractor = VERSION_EXTRACTORS.get(kind)
        if version_extractor is not None:
            extracted = version_extractor(content)
            if extracted is not None:
                source.solution_version, source.solution_fix = extracted
                source.save(update_fields=["solution_version", "solution_fix"])

        sync_func = SYNC_FUNCS[kind]
        sync_func(source, sections)

        return Response(
            {"asset_id": asset.id, "hostname": asset.hostname, "kind": kind, "updated": True},
            status=status.HTTP_201_CREATED,
        )
