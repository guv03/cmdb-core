"""was/sync.py의 _resolve_webtob_asset과 같은 패턴 - hostname 매칭을 먼저 시도하고 안 되면
primary_ip로 재시도한다. 다만 primary_ip(GenericIPAddressField)는 IP 형식이 아닌 문자열로
조회하면 DB 어댑터 단에서 바로 ValueError가 나므로(hostname도 IP도 아닌 값을 등록했을 때),
IP 형식일 때만 그 조회를 시도한다."""

import ipaddress

from core.models import Asset
from core.reconciliation import normalize_hostname


def resolve_backend_asset(ip_or_hostname: str) -> Asset | None:
    if not ip_or_hostname:
        return None
    asset = Asset.objects.filter(hostname=normalize_hostname(ip_or_hostname)).first()
    if asset is not None:
        return asset

    try:
        ipaddress.ip_address(ip_or_hostname)
    except ValueError:
        return None
    return Asset.objects.filter(primary_ip=ip_or_hostname).first()
