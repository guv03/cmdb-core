from network.models import ServiceNetworkBackend
from network.resolve import resolve_backend_asset


def sync_backends(mapping, entries: list[str]) -> None:
    """대시보드에서 제출한 백엔드 목록(줄바꿈 구분 문자열을 view에서 미리 리스트로 정리해 전달)
    으로 통짜 교체한다. push가 아니라 사람이 그 자리에서 편집 제출한 값이라 diff 이력 없이
    바로 반영해도 안전하다(webconfig/was의 구조화 테이블 통짜 교체와 같은 이유)."""
    mapping.backends.all().delete()
    backends = []
    for raw in entries:
        value = raw.strip()
        if not value:
            continue
        backends.append(
            ServiceNetworkBackend(mapping=mapping, ip_or_hostname=value, asset=resolve_backend_asset(value))
        )
    ServiceNetworkBackend.objects.bulk_create(backends)
