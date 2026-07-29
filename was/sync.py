from django.db import transaction

from core.models import Asset
from core.reconciliation import normalize_hostname
from was.models import JeusContainer, JeusWebtobConnector, WasConfigSource
from webconfig.models import WebConfigSource, WebtobServer


def _resolve_asset(node_name: str) -> Asset | None:
    """자산 신규 생성은 facts push 경로 하나뿐이라는 원칙 유지 - 찾지 못하면 None
    (호출부가 컨테이너/커넥터 단위로 관대하게 null 처리)."""
    if not node_name:
        return None
    return Asset.objects.filter(hostname=normalize_hostname(node_name)).first()


def _resolve_webtob_asset(network_address: str) -> Asset | None:
    """network-address는 hostname일 수도 실제 IP일 수도 있어 hostname 매칭을 먼저
    시도하고, 안 되면 primary_ip로 재시도한다."""
    if not network_address:
        return None
    asset = Asset.objects.filter(hostname=normalize_hostname(network_address)).first()
    if asset is not None:
        return asset
    return Asset.objects.filter(primary_ip=network_address).first()


def _resolve_webtob_server(registration_id: str, webtob_asset: Asset | None) -> WebtobServer | None:
    """registration-id는 WebToB *SERVER(SVRTYPE=JSV)의 이름 자체와 매칭된다."""
    if webtob_asset is None or not registration_id:
        return None
    return WebtobServer.objects.filter(
        name=registration_id,
        source__asset=webtob_asset,
        source__kind=WebConfigSource.Kind.WEBTOB,
    ).first()


def _resolve_webtob_service_name(webtob_servers: list[WebtobServer]) -> str | None:
    """연결된 WebtobServer들의 SvrGroup에 걸린 vhost service_name을 모아, 공백 아닌 값이
    정확히 하나로 겹치면 그 값을 돌려준다(이중화 - 같은 서비스가 여러 WebToB 서버로 붙는
    일반적인 경우). 값이 갈리면(서로 다른 서비스가 섞인 이상 케이스) None을 반환해
    호출부가 기존 service_name을 그대로 두게 한다."""
    names = set()
    for server in webtob_servers:
        if server.svrgroup_id is None:
            continue
        for vhost in server.svrgroup.vhosts.all():
            if vhost.service_name:
                names.add(vhost.service_name)
    if len(names) == 1:
        return next(iter(names))
    return None


@transaction.atomic
def sync_jeus8(source: WasConfigSource, parsed: dict) -> None:
    """파싱된 컨테이너 목록으로 이 source에 딸린 JeusContainer/JeusWebtobConnector를
    재생성한다. 컨테이너는 이름으로 upsert(수기 입력한 service_name 보존), webtob 커넥터는
    MANUAL 필드가 없어 컨테이너별로 통짜 재생성."""
    seen_names = []
    for attrs in parsed.get("containers", []):
        name = attrs["name"]
        container, _ = JeusContainer.objects.update_or_create(
            source=source,
            name=name,
            defaults=dict(
                asset=_resolve_asset(attrs.get("node_name", "")),
                node_name=attrs.get("node_name", ""),
                listen_port=attrs.get("listen_port", ""),
                ssl_port=attrs.get("ssl_port", ""),
                deployed_apps_summary=attrs.get("deployed_apps_summary", ""),
            ),
        )
        seen_names.append(name)

        JeusWebtobConnector.objects.filter(container=container).delete()
        webtob_servers = []
        for connector_attrs in attrs.get("webtob_connectors", []):
            webtob_asset = _resolve_webtob_asset(connector_attrs.get("network_address", ""))
            webtob_server = _resolve_webtob_server(
                connector_attrs.get("registration_id", ""), webtob_asset
            )
            JeusWebtobConnector.objects.create(
                container=container,
                name=connector_attrs.get("name", ""),
                registration_id=connector_attrs.get("registration_id", ""),
                network_address=connector_attrs.get("network_address", ""),
                port=connector_attrs.get("port", ""),
                wjp_version=connector_attrs.get("wjp_version", ""),
                webtob_server=webtob_server,
            )
            if webtob_server is not None:
                webtob_servers.append(webtob_server)

        # WebToB 쪽 서비스명을 따라간다(AUTO-if-resolvable, 아니면 기존 수기 입력 값 유지) -
        # 이중화로 여러 connector가 붙어도 실제 서비스명이 같으면 자동으로 채워짐.
        resolved_service_name = _resolve_webtob_service_name(webtob_servers)
        if resolved_service_name is not None:
            container.service_name = resolved_service_name
            container.save(update_fields=["service_name"])

    JeusContainer.objects.filter(source=source).exclude(name__in=seen_names).delete()
