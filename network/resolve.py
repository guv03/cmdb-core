"""was/sync.py의 _resolve_webtob_asset과 같은 패턴 - hostname 매칭을 먼저 시도하고 안 되면
primary_ip로 재시도한다. 다만 primary_ip(GenericIPAddressField)는 IP 형식이 아닌 문자열로
조회하면 DB 어댑터 단에서 바로 ValueError가 나므로(hostname도 IP도 아닌 값을 등록했을 때),
IP 형식일 때만 그 조회를 시도한다."""

import ipaddress
import re

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


def find_matching_route(text: str, routes_by_key: dict):
    """text(예: Apache/Nginx vhost의 proxy_summary) 안에서 NetworkRoute.key가 부분 문자열로
    포함되는 라우트를 찾는다. 키 길이가 긴 것부터 확인해 "10.0.0.1"이 "10.0.0.10"의 일부로
    오탐되는 걸 막고, 일치 앞뒤가 영숫자/점이 아닐 때만(단어 경계) 진짜 일치로 본다."""
    if not text:
        return None
    for key in sorted(routes_by_key, key=len, reverse=True):
        pattern = r"(?<![\w.])" + re.escape(key) + r"(?![\w.])"
        if re.search(pattern, text):
            return routes_by_key[key]
    return None


def resolve_chain(start_text: str, routes_by_key: dict) -> list:
    """proxy_summary 같은 텍스트에서 시작해 NetworkRoute 체인을 재귀적으로 따라간다. 각 홉에서
    backends 중 다른 라우트의 key와 일치하는 게 있으면 그걸 다음 홉으로 삼아 계속 이어간다
    (여러 개면 ip_or_hostname 오름차순으로 첫 번째만 - 한 라우트가 여러 하위 라우트로 갈라지는
    분기까지는 다루지 않는다, MVP 범위). 순환 참조가 있으면 그 라우트에서 체인을 끊는다.

    반환값은 [route, route, ...] 순서 리스트(마지막 라우트의 backends 중 다른 라우트와 안
    겹치는 값들이 최종 실서버)."""
    chain = []
    visited_ids: set = set()
    route = find_matching_route(start_text, routes_by_key)
    while route is not None and route.id not in visited_ids:
        visited_ids.add(route.id)
        chain.append(route)
        next_route = None
        for backend in sorted(route.backends.all(), key=lambda b: b.ip_or_hostname):
            candidate = routes_by_key.get(backend.ip_or_hostname)
            if candidate is not None:
                next_route = candidate
                break
        route = next_route
    return chain
