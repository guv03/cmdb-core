import json

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import AWXAPIKeyAuthentication
from database.models import DbConfigSource, DbConfigSourceRevision
from database.parsers import PARSERS, ParseError
from database.serializers import DbConfigIngestSerializer
from database.sync import parse_dt, resolve_asset, sync_database


def _extract_collection_hostname(parsed: dict) -> str | None:
    """WAS의 admin-server-name과 같은 원리 - content 안에서 결정적으로 뽑는다(AWX가 별도
    hostname 필드를 보낼 필요 없음). SQL이 SYS_CONTEXT('USERENV','INSTANCE_NAME')으로 자기
    자신이 실행 중인 인스턴스명을 'collected_from_instance'로 같이 실어 보내면, instances
    목록에서 그 인스턴스를 찾아 host_name을 쓴다(awx/push_oracle_config_to_cmdb.yml 참고).
    Standalone은 인스턴스가 하나뿐이라 항상 그 값과 일치. 이 키가 없으면(과거 롤아웃 이전
    버전 등) None을 돌려주고 호출부가 asset=null로 관대하게 처리한다."""
    collected_from = parsed.get("collected_from_instance")
    if not collected_from:
        return None
    for instance in parsed.get("instances", []):
        if instance["instance_name"] == collected_from:
            return instance.get("host_name") or None
    return None


class DbConfigIngestView(APIView):
    """AWX가 DB 호스트(RAC면 대표 노드 1대만 인벤토리에 넣을 것)에서 로컬로 실행한 sqlplus
    조회 결과(JSON)를 push하는 엔드포인트. 자산은 신규 생성하지 않는다(자산 생성은 facts
    push 경로 하나뿐이라는 원칙 유지) - 이번 push를 실행한 노드의 hostname으로 찾아
    DbConfigSource.asset에 연결하고, 못 찾으면 asset=null(관대한 원칙, 다음 push 때 재해석).
    개별 인스턴스(DbInstance)의 자산 연결은 각자의 host_name으로 sync 단계에서 따로 처리한다
    (RAC는 소스를 실행한 노드와 각 인스턴스가 속한 노드가 다를 수 있음)."""

    authentication_classes = [AWXAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DbConfigIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kind = serializer.validated_data["kind"]
        content = serializer.validated_data["content"]
        # 정상 케이스는 이미 문자열이라 그대로 통과. dict/list로 온 경우(Ansible native
        # jinja가 순수 JSON 텍스트를 문자열이 아니라 Python 리터럴로 오인 변환하는 경우가
        # 실측 확인됨 - serializers.py 참고)는 문자열로 재직렬화해 이후 로직(파싱/저장/diff)이
        # 항상 문자열만 다루도록 통일한다.
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)

        parser = PARSERS.get(kind)
        if parser is None:
            return Response({"error": f"지원하지 않는 kind: {kind}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parsed = parser(content)
        except ParseError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        hostname = _extract_collection_hostname(parsed)
        asset = resolve_asset(hostname) if hostname else None

        existing = DbConfigSource.objects.filter(
            kind=kind, db_unique_name=parsed["db_unique_name"]
        ).first()
        if existing is not None and existing.raw_content != content:
            DbConfigSourceRevision.objects.create(
                source=existing, old_content=existing.raw_content, new_content=content
            )

        source, _ = DbConfigSource.objects.update_or_create(
            kind=kind,
            db_unique_name=parsed["db_unique_name"],
            defaults={
                "asset": asset,
                "db_name": parsed.get("db_name", ""),
                "database_role": parsed.get("database_role", ""),
                "open_mode": parsed.get("open_mode", ""),
                "log_mode": parsed.get("log_mode", ""),
                "characterset": parsed.get("characterset", ""),
                "platform_name": parsed.get("platform_name", ""),
                "db_created_at": parse_dt(parsed.get("created")),
                "raw_content": content,
                "extra": parsed.get("extra") or {},
            },
        )

        sync_database(source, parsed)

        return Response(
            {
                "db_unique_name": source.db_unique_name,
                "kind": kind,
                "asset_id": asset.id if asset else None,
                "instance_count": source.instances.count(),
                "updated": True,
            },
            status=status.HTTP_201_CREATED,
        )
