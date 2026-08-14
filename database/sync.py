from django.db import transaction
from django.utils.dateparse import parse_datetime

from core.models import Asset
from core.reconciliation import normalize_hostname
from database.dynamic_fields import sync_source_fields
from database.models import DbConfigSource, DbInstance


def resolve_asset(host_name: str) -> Asset | None:
    """자산 신규 생성은 facts push 경로 하나뿐이라는 원칙 유지 - 찾지 못하면 None
    (호출부가 소스/인스턴스 단위로 관대하게 null 처리)."""
    if not host_name:
        return None
    return Asset.objects.filter(hostname=normalize_hostname(host_name)).first()


def parse_dt(value):
    if not value:
        return None
    return parse_datetime(value)


@transaction.atomic
def sync_database(source: DbConfigSource, parsed: dict) -> None:
    """파싱된 인스턴스 목록으로 이 source에 딸린 DbInstance를 통짜 재생성한다(WebtobVhost/
    SystemVm과 동일 패턴 - RAC는 대표 노드 한 곳에서 GV$ 조회만으로 클러스터 전체가 매번
    다시 나오므로 diff 없이 교체가 자연스럽다. DbInstance는 MANUAL 개념이 없어 통짜 교체가
    안전). DbConfigSource 자신의 upsert/revision 기록은 호출부(database/views.py)가 이미
    끝낸 뒤 이 함수를 부른다 - was.sync.sync_jeus와 동일한 책임 분담."""
    source.instances.all().delete()
    for item in parsed.get("instances", []):
        DbInstance.objects.create(
            source=source,
            asset=resolve_asset(item.get("host_name", "")),
            instance_name=item["instance_name"],
            instance_number=item.get("instance_number"),
            host_name=item.get("host_name", ""),
            version=item.get("version", ""),
            status=item.get("status", ""),
            archiver=item.get("archiver", ""),
            startup_time=parse_dt(item.get("startup_time")),
            listener_port=item.get("listener_port", ""),
            extra=item.get("extra") or {},
        )

    # AUTO 동적 필드는 source.extra가 이미 최신으로 저장된 뒤(views.py) 호출되므로 여기서
    # 바로 재계산해도 안전하다.
    sync_source_fields(source)
