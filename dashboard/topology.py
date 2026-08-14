"""서비스 구성도(System-OS-WEB/WAS) 그래프 생성 + Graphviz(dot) 렌더링.

표/레인 방식은 WEB vhost/WAS 컨테이너가 여러 대로 이중화된 경우(같은 물리 서버가 레인마다
반복 표시) 어떤 게 같은 서버인지 한눈에 안 들어오는 문제가 있어 기각했다. 대신 실제
그래프 구조(같은 자산/물리호스트는 노드 하나로 중복 제거, 연결된 것만 엣지)를 만들어
Graphviz(dot)로 서버에서 SVG를 그려 내려준다 - 클라이언트 JS 없이 이중화(N:M 연결)도
레이아웃 엔진이 알아서 안 겹치게 배치해준다. Mermaid(브라우저 렌더링)도 검토했으나
System>OS>App 3단 중첩 표현이 Graphviz cluster가 더 정교해서 이쪽으로 결정."""

import subprocess

from django.urls import reverse

from systems.models import SystemVm
from was.models import JeusContainer, JeusDataSource, JeusWebtobConnector
from webconfig.models import ApacheVhost, NginxVhost, WebtobVhost


def _system_host_for_asset(asset):
    """asset이 vCenter/Nutanix VM으로도 잡혀있으면 그 물리 호스트를 돌려준다 - 매칭된 VM이
    여러 개(같은 asset이 여러 소스에 잡히는 드문 경우)라도 첫 번째만 쓴다(구성도는 "어디
    즈음에 떠있나"를 보여주는 용도라 완전한 목록보다 간단한 매칭 하나로 충분)."""
    if asset is None:
        return None
    vm = (
        SystemVm.objects.filter(asset=asset)
        .exclude(host=None)
        .select_related("host", "host__source")
        .first()
    )
    return vm.host if vm else None


def _vhost_endpoint_label(vhost) -> str | None:
    """도메인이 있는 vhost만 http(s)://도메인:포트 형태로 만든다 - TLS 여부(ssl_flag)로
    프로토콜을 결정. 도메인이 없는 vhost(WebToB 내부 전용 등)는 None(호출부가 이름만 표시)."""
    if not vhost.hostname:
        return None
    protocol = "https" if vhost.ssl_flag else "http"
    if vhost.port:
        return f"{protocol}://{vhost.hostname}:{vhost.port}"
    return f"{protocol}://{vhost.hostname}"


def build_service_topology_graph(service) -> dict:
    """서비스 하나에 걸린 WEB vhost/WAS 컨테이너를 노드로, WebToB<->JEUS 실제 연결
    (JeusWebtobConnector)과 JEUS<->DB 실제 연결(JeusDataSource.db_instance)만 엣지로
    만든다. 같은 asset을 가리키는 노드는 나중에 render_topology_svg에서 OS 클러스터
    하나로 자동 합쳐진다 - 여기서는 각 노드가 자기 asset을 들고 있기만 하면 된다.

    DB는 WEB/WAS와 달리 서비스가 직접 배정되는 대상이 아니라서(서비스는 vhost/컨테이너에만
    배정) DB 노드는 이 그래프에 이미 들어간 WAS 컨테이너가 참조하는 데이터소스를 따라가서
    간접적으로만 편입된다 - "이 서비스가 쓰는 DB"가 아니라 "이 서비스의 WAS 컨테이너가
    실제로 붙는 DB"라는 뜻이라 WebToB<->JEUS 엣지와 성격이 같다(둘 다 실제 연결을 따라가는
    것이지 서비스 배정을 따라가는 게 아님)."""
    webtob_vhosts = list(WebtobVhost.objects.filter(service=service).select_related("source__asset"))
    apache_vhosts = list(ApacheVhost.objects.filter(service=service).select_related("source__asset"))
    nginx_vhosts = list(NginxVhost.objects.filter(service=service).select_related("source__asset"))
    containers = list(JeusContainer.objects.filter(service=service).select_related("asset", "source"))
    container_ids = {c.id for c in containers}

    nodes = []
    web_node_id_by_vhost = {}
    for kind, vhosts in (
        ("webtob", webtob_vhosts),
        ("apache", apache_vhosts),
        ("nginx", nginx_vhosts),
    ):
        for vhost in vhosts:
            node_id = f"web_{kind}_{vhost.id}"
            endpoint = _vhost_endpoint_label(vhost)
            label_lines = [vhost.source.get_kind_display()]
            if kind == "webtob":
                # WebToB는 SvrGroup/커넥터가 참조하는 내부 식별자(vhost.name)가 도메인과
                # 별개로 의미 있어 항상 같이 보여준다(apache/nginx의 name은 "hostname:port"
                # 합성값이라 endpoint와 중복이라 굳이 안 보여줌).
                label_lines.append(vhost.name)
            label_lines.append(endpoint or (vhost.name if kind != "webtob" else None))
            label = "\n".join(line for line in label_lines if line)
            nodes.append(
                {
                    "id": node_id,
                    "label": label,
                    "asset": vhost.source.asset,
                    "detail_url": reverse("dashboard-webconfig-detail", args=[vhost.source_id]),
                }
            )
            if kind == "webtob":
                web_node_id_by_vhost[vhost.id] = node_id

    was_node_id_by_container = {}
    for container in containers:
        node_id = f"was_{container.id}"
        nodes.append(
            {
                "id": node_id,
                "label": f"{container.source.get_kind_display()}\n{container.name}",
                "asset": container.asset,
                "detail_url": reverse("dashboard-was-detail", args=[container.source_id]),
            }
        )
        was_node_id_by_container[container.id] = node_id

    edges = []
    if webtob_vhosts:
        connectors = (
            JeusWebtobConnector.objects.filter(
                webtob_server__svrgroup__vhosts__in=webtob_vhosts,
                container_id__in=container_ids,
            )
            .prefetch_related("webtob_server__svrgroup__vhosts")
            .distinct()
        )
        for connector in connectors:
            to_id = was_node_id_by_container[connector.container_id]
            for vhost in connector.webtob_server.svrgroup.vhosts.all():
                from_id = web_node_id_by_vhost.get(vhost.id)
                if from_id is not None:
                    edges.append(
                        {"from": from_id, "to": to_id, "label": connector.name or connector.registration_id}
                    )

    if container_ids:
        # 이 서비스의 WAS 컨테이너가 참조하는 데이터소스 중 DB 쪽 매칭(db_instance)이 실제로
        # 된 것만 - JeusDataSource.db_instance가 was/sync.py에서 push 시점에 이미 해석해둔
        # 값을 그대로 따라간다(여기서 새로 매칭하지 않음). 같은 DbInstance를 여러 컨테이너가
        # 공유할 수 있어 노드는 instance당 하나만 만들고 엣지만 컨테이너 수만큼 추가한다.
        data_sources = (
            JeusDataSource.objects.filter(containers__id__in=container_ids, db_instance__isnull=False)
            .select_related("db_instance__source", "db_instance__asset")
            .prefetch_related("containers")
            .distinct()
        )
        db_node_id_by_instance = {}
        for data_source in data_sources:
            instance = data_source.db_instance
            node_id = db_node_id_by_instance.get(instance.id)
            if node_id is None:
                node_id = f"db_{instance.id}"
                db_node_id_by_instance[instance.id] = node_id
                nodes.append(
                    {
                        "id": node_id,
                        "label": f"{instance.source.get_kind_display()}\n{instance.source.db_unique_name}\n{instance.instance_name}",
                        "asset": instance.asset,
                        "detail_url": reverse("dashboard-db-config-detail", args=[instance.source_id]),
                    }
                )
            for container in data_source.containers.all():
                from_id = was_node_id_by_container.get(container.id)
                if from_id is not None:
                    edges.append({"from": from_id, "to": node_id, "label": data_source.data_source_id})

    return {"nodes": nodes, "edges": edges}


def _dot_escape(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_topology_svg(graph: dict) -> str:
    """build_service_topology_graph 결과를 dot 텍스트로 바꿔 graphviz(dot 바이너리, 이미지에
    apt로 설치됨)로 SVG를 렌더링한다. 노드는 asset(OS) -> 그 asset의 물리호스트(System)
    순으로 묶어 중첩 cluster로 만든다 - 같은 asset을 쓰는 노드가 여러 개면 자연히 한
    OS 박스 안에 같이 들어간다(예: 같은 서버에 WebToB/JEUS가 같이 뜬 경우)."""
    by_system: dict = {}
    for node in graph["nodes"]:
        asset = node["asset"]
        system = _system_host_for_asset(asset) if asset else None
        system_key = system.id if system else None
        asset_key = asset.id if asset else f"__unmatched_{node['id']}"

        system_group = by_system.setdefault(system_key, {"system": system, "assets": {}})
        asset_group = system_group["assets"].setdefault(asset_key, {"asset": asset, "nodes": []})
        asset_group["nodes"].append(node)

    lines = [
        "digraph service_topology {",
        "  rankdir=LR;",
        '  bgcolor="white";',
        '  node [shape=box, style="rounded,filled", fillcolor="white", '
        'fontname="Malgun Gothic,sans-serif", fontsize=12, margin="0.15,0.1"];',
        '  edge [fontsize=10, fontname="Malgun Gothic,sans-serif", color="#3273dc", '
        "penwidth=1.6, arrowsize=0.8];",
    ]

    cluster_idx = 0
    for system_group in by_system.values():
        system = system_group["system"]
        indent = "  "
        if system is not None:
            lines.append(f"{indent}subgraph cluster_{cluster_idx} {{")
            cluster_idx += 1
            label = f"System · {system.name or system.external_id} ({system.source.get_kind_display()})"
            lines.append(f"{indent}  label={_dot_escape(label)};")
            lines.append(f'{indent}  style="dashed"; color="#999999"; fontsize=10; fontcolor="#666666";')
            lines.append(f'{indent}  URL={_dot_escape(reverse("dashboard-system-detail", args=[system.pk]))};')
            indent = "    "

        for asset_group in system_group["assets"].values():
            asset = asset_group["asset"]
            lines.append(f"{indent}subgraph cluster_{cluster_idx} {{")
            cluster_idx += 1
            if asset is not None:
                hostfact = getattr(asset, "hostfact", None)
                os_family = hostfact.os_family if hostfact and hostfact.os_family else "OS"
                hostname_part = asset.hostname.upper()
                if asset.primary_ip:
                    hostname_part = f"{hostname_part} ({asset.primary_ip})"
                label = f"{os_family} · {hostname_part}"
            else:
                label = "OS · (미등록)"
            lines.append(f"{indent}  label={_dot_escape(label)};")
            lines.append(f'{indent}  style="filled"; color="#cccccc"; fillcolor="#f2f2f2"; fontsize=10;')
            if asset is not None:
                lines.append(f'{indent}  URL={_dot_escape(reverse("dashboard-asset-detail", args=[asset.pk]))};')
            for node in asset_group["nodes"]:
                url_attr = f', URL={_dot_escape(node["detail_url"])}' if node.get("detail_url") else ""
                lines.append(f'{indent}  {node["id"]} [label={_dot_escape(node["label"])}{url_attr}];')
            lines.append(f"{indent}}}")

        if system is not None:
            lines.append("  }")

    for edge in graph["edges"]:
        lines.append(f'  {edge["from"]} -> {edge["to"]} [label={_dot_escape(edge["label"] or "")}];')

    lines.append("}")
    dot_text = "\n".join(lines)

    result = subprocess.run(
        ["dot", "-Tsvg"],
        input=dot_text.encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "ignore"))
    return result.stdout.decode("utf-8")
