from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from core.models import Asset
from core.reconciliation import normalize_hostname
from was.models import WasConfigSource, WasConfigSourceRevision
from was.parsers import PARSERS
from was.serializers import WasConfigIngestSerializer
from was.sync import sync_jeus

SYNC_FUNCS = {
    WasConfigSource.Kind.JEUS: sync_jeus,
    # parse_jeus6도 parse_jeus와 같은 반환 형태({"containers": [...], "data_sources": [...]})라
    # sync_jeus를 그대로 재사용 - kind별 동기화 로직 분기가 필요 없음.
    WasConfigSource.Kind.JEUS6: sync_jeus,
}


def _extract_admin_hostname(kind: str, parsed: dict) -> str | None:
    """WebToB의 *NODE절과 같은 원리 - content 안에서 결정적으로 뽑는다(AWX가 별도
    hostname을 보낼 필요 없음). JEUS(7+)는 admin-server-name에 해당하는 컨테이너의
    node-name이 이 push를 보낸(=admin 서버가 떠있는) 호스트의 hostname이다. JEUS6은
    admin 서버 개념 자체가 없고 JEUSMain.xml 하나 = 물리 노드 하나라 최상위 node_name을
    그대로 쓴다(was/parsers.py의 parse_jeus6)."""
    if kind == WasConfigSource.Kind.JEUS:
        admin_server_name = parsed.get("admin_server_name")
        if not admin_server_name:
            return None
        for container in parsed.get("containers", []):
            if container.get("name") == admin_server_name:
                return container.get("node_name") or None
        return None
    if kind == WasConfigSource.Kind.JEUS6:
        return parsed.get("node_name") or None
    return None


def _combine_jeus6_files_for_display(files: dict) -> str:
    """JEUS6은 파일이 여러 개라 raw_content(단일 TextField)엔 사람이 구분해서 읽을 수 있게
    파일 경계를 표시한 텍스트로 합쳐서 저장한다("원본 설정 보기"/변경 이력 diff용) - 파싱은
    항상 원본 files(dict)로 하고(was/parsers.py의 parse_jeus6) 이 합본은 표시 전용이라
    구분자 형식이 파싱 로직과 절대 안 섞인다."""
    parts = [f"===== {name} =====\n{content}" for name, content in sorted(files.items())]
    return "\n\n".join(parts)


class WasConfigIngestView(APIView):
    """AWX가 WAS 설정 원본 텍스트를 push하는 엔드포인트. 자산은 admin 서버 컨테이너의
    node-name으로 찾는다(신규 생성은 안 함 - 자산 생성은 facts push 경로 하나뿐이라는
    원칙 유지). domain.xml에 담긴 개별 컨테이너는 이 소스의 asset과 다른 자산에 속할 수
    있어 컨테이너별 자산 연결은 sync 단계(was/sync.py)에서 따로 처리한다."""

    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WasConfigIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kind = serializer.validated_data["kind"]
        # kind=jeus는 항상 빈 문자열(도메인 하나 = admin 서버 하나라 구분값이 필요 없음) -
        # kind=jeus6만 실제 값이 들어온다(같은 호스트에 OS 계정별로 여러 인스턴스가 뜰 수
        # 있어서, WasConfigSource.instance_name 참고).
        instance_name = serializer.validated_data.get("instance_name", "")

        parser = PARSERS.get(kind)
        if parser is None:
            return Response({"error": f"지원하지 않는 kind: {kind}"}, status=status.HTTP_400_BAD_REQUEST)

        if kind == WasConfigSource.Kind.JEUS6:
            files = serializer.validated_data["files"]
            parsed = parser(files)
            content = _combine_jeus6_files_for_display(files)
        else:
            content = serializer.validated_data["content"]
            parsed = parser(content)

        hostname = _extract_admin_hostname(kind, parsed)
        if not hostname:
            return Response(
                {"error": "설정 내용에서 admin 서버 호스트명을 찾지 못했습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset = Asset.objects.filter(hostname=normalize_hostname(hostname)).first()
        if asset is None:
            return Response(
                {"error": f"등록되지 않은 자산입니다(먼저 facts push로 등록 필요): {hostname}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = WasConfigSource.objects.filter(
            asset=asset, kind=kind, instance_name=instance_name
        ).first()
        if existing is not None and existing.raw_content != content:
            WasConfigSourceRevision.objects.create(
                source=existing, old_content=existing.raw_content, new_content=content
            )

        source, _ = WasConfigSource.objects.update_or_create(
            asset=asset,
            kind=kind,
            instance_name=instance_name,
            defaults={"raw_content": content, "solution_version": parsed.get("domain_version", "")},
        )

        sync_func = SYNC_FUNCS[kind]
        sync_func(source, parsed)

        return Response(
            {
                "asset_id": asset.id,
                "hostname": asset.hostname,
                "kind": kind,
                "instance_name": instance_name,
                "updated": True,
            },
            status=status.HTTP_201_CREATED,
        )
