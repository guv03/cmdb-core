import json


class ParseError(Exception):
    """content가 유효한 JSON이 아니거나 최소 필수 키(db_unique_name)가 없는 경우."""


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_oracle(content: str) -> dict:
    """AWX가 sqlplus로 실행한 JSON_OBJECT/JSON_ARRAYAGG SQL의 출력(JSON 문자열)을 그대로
    파싱한다(awx/push_oracle_config_to_cmdb.yml 참고). Oracle 12c/19c 둘 다 JSON_OBJECT/
    JSON_ARRAYAGG를 지원해서 DB 자신이 이미 우리가 원하는 키 이름(snake_case)으로 JSON을
    만들어주므로 WebToB/Apache처럼 텍스트를 정규식으로 긁어내는 파서가 필요 없다 - json.loads
    후 최소 형태만 방어적으로 정리한다.

    RAC 여부와 무관하게 항상 같은 모양이다 - gv$instance는 Standalone에서도 그냥 1행짜리
    v$instance와 동일하게 동작하므로, AWX 쪽 SQL/플레이북이 kind 분기 없이 항상 gv$를 조회하고
    이 파서도 kind 분기가 필요 없다."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ParseError(f"유효한 JSON이 아닙니다: {exc}") from exc

    if not isinstance(data, dict):
        raise ParseError("최상위 값이 JSON object가 아닙니다.")

    db_unique_name = str(data.get("db_unique_name") or "").strip()
    if not db_unique_name:
        raise ParseError("db_unique_name이 없습니다.")

    instances = []
    for item in data.get("instances") or []:
        if not isinstance(item, dict):
            continue
        instance_name = str(item.get("instance_name") or "").strip()
        if not instance_name:
            continue
        instances.append(
            {
                "instance_name": instance_name,
                "instance_number": _int_or_none(item.get("instance_number")),
                "host_name": str(item.get("host_name") or "").strip(),
                "version": item.get("version") or "",
                "status": item.get("status") or "",
                "archiver": item.get("archiver") or "",
                "startup_time": item.get("startup_time") or "",
                "listener_port": str(item.get("listener_port") or ""),
                # 인스턴스별 원본 전체 - 지금은 동적 필드 대상이 아니지만(모델 참고)
                # 감사/향후 확장용으로 그대로 보관.
                "extra": item,
            }
        )

    return {
        "db_unique_name": db_unique_name,
        # database/views.py의 _extract_collection_hostname이 이 값으로 instances 목록에서
        # "이번 push를 실행한 노드"를 찾는다(WAS의 admin_server_name과 동일한 역할) - extra
        # 안에도 원본 그대로 들어있지만(동적 필드 dot-path 대상), 매칭 로직은 최상위에서
        # 바로 꺼내 쓰도록 별도로 승격해둔다.
        "collected_from_instance": str(data.get("collected_from_instance") or ""),
        "db_name": data.get("db_name") or "",
        "database_role": data.get("database_role") or "",
        "open_mode": data.get("open_mode") or "",
        "log_mode": data.get("log_mode") or "",
        "characterset": data.get("characterset") or "",
        "platform_name": data.get("platform_name") or "",
        "created": data.get("created") or "",
        # instances를 뺀 database 레벨 원본 전체 - DbConfigSourceFieldDefinition(AUTO)이
        # 여기서 dot-path로 값을 뽑는다(고정 컬럼으로 승격된 키도 중복 포함, systems 앱의
        # SystemHost.extra와 동일 원칙).
        "extra": {k: v for k, v in data.items() if k != "instances"},
        "instances": instances,
    }


PARSERS = {
    "oracle": parse_oracle,
}
