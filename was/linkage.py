"""WebToB<->JEUS 연결 그래프를 가로지르는 서비스 배정 헬퍼. `was`가 이미 `webconfig`에
의존하는 방향과 같은 선상이라 여기 둔다(반대 방향으로 webconfig가 was를 알게 만들지 않음).

대시보드 "서비스" 탭에서 사람이 vhost 또는 컨테이너 중 한쪽의 서비스를 직접 고치면,
JeusWebtobConnector로 실제 연결된 반대쪽도 같은 core.Service를 가리키도록 즉시 맞춘다
(push 시점 자동 해석과 달리 사람이 명시적으로 지정한 값이라 애매함 없이 그냥 이긴다) -
다만 연결된 쪽에 이미 다른 서비스가 들어있으면 그냥 덮어쓰지 않고 호출부가 먼저
확인받을 수 있도록 충돌 정보만 돌려준다(force=True면 확인 없이 그대로 진행)."""

from webconfig.models import WebServiceDomain, WebtobVhost


def get_connected_containers(vhost: WebtobVhost):
    """이 vhost가 걸린 SvrGroup의 Server(WebToB)에 연결된 WasContainer 전체(중복 제거).
    SvrGroup-vhost M2M 조인이라 .distinct()가 필요한데, WasContainer.deployed_apps_summary가
    TextField(Oracle NCLOB)라 그대로 두면 ORA-00932가 남 - 여기서 그 값을 쓰지 않으므로 defer."""
    from was.models import WasContainer

    return WasContainer.objects.filter(
        webtob_connectors__webtob_server__svrgroup__vhosts=vhost
    ).defer("deployed_apps_summary").distinct()


def get_connected_vhosts(container) -> "list[WebtobVhost]":
    """get_connected_containers의 반대 방향 - 이 컨테이너의 webtob-connector가 연결된
    WebtobServer의 SvrGroup에 걸린 vhost 전체(중복 제거)."""
    return list(
        WebtobVhost.objects.filter(
            svrgroups__servers__jeus_connectors__container=container
        ).distinct()
    )


def _conflicting_peers(peers, service):
    """service와 다르면서 이미 값이 있는 peer만 추려서 반환 - 비어있거나 같은 값은 충돌 아님."""
    target_id = service.id if service else None
    return [p for p in peers if p.service_id and p.service_id != target_id]


def _sync_web_service_domains(vhosts, service):
    for vhost in vhosts:
        WebServiceDomain.objects.filter(source=vhost.source, vhost_name=vhost.name).update(
            service_name=service.name if service else ""
        )


def apply_vhost_service(vhost: WebtobVhost, service, force: bool = False) -> dict:
    """vhost.service를 바꾸고 연결된 WasContainer 전체에 전파한다."""
    from was.models import WasContainer

    containers = list(get_connected_containers(vhost))
    conflicts = _conflicting_peers(containers, service)
    if conflicts and not force:
        return {
            "conflict": True,
            "peer_labels": [
                f"{c.asset.hostname if c.asset else c.node_name}/{c.name}" for c in conflicts
            ],
        }

    vhost.service = service
    vhost.save(update_fields=["service"])
    _sync_web_service_domains([vhost], service)
    if containers:
        WasContainer.objects.filter(id__in=[c.id for c in containers]).update(service=service)

    return {"conflict": False, "propagated_count": len(containers)}


def apply_container_service(container, service, force: bool = False) -> dict:
    """apply_vhost_service의 반대 방향 - container.service를 바꾸고 연결된 vhost 전체에 전파."""
    vhosts = get_connected_vhosts(container)
    conflicts = _conflicting_peers(vhosts, service)
    if conflicts and not force:
        return {
            "conflict": True,
            "peer_labels": [f"{v.source.asset.hostname}/{v.name}" for v in conflicts],
        }

    container.service = service
    container.save(update_fields=["service"])
    if vhosts:
        WebtobVhost.objects.filter(id__in=[v.id for v in vhosts]).update(service=service)
        _sync_web_service_domains(vhosts, service)

    return {"conflict": False, "propagated_count": len(vhosts)}
