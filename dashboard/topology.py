"""서비스 구성도(System-OS-WEB/WAS) 그래프 생성 + Graphviz(dot) 렌더링.

표/레인 방식은 WEB vhost/WAS 컨테이너가 여러 대로 이중화된 경우(같은 물리 서버가 레인마다
반복 표시) 어떤 게 같은 서버인지 한눈에 안 들어오는 문제가 있어 기각했다. 대신 실제
그래프 구조(같은 자산/물리호스트는 노드 하나로 중복 제거, 연결된 것만 엣지)를 만들어
Graphviz(dot)로 서버에서 SVG를 그려 내려준다 - 클라이언트 JS 없이 이중화(N:M 연결)도
레이아웃 엔진이 알아서 안 겹치게 배치해준다. Mermaid(브라우저 렌더링)도 검토했으나
System>OS>App 3단 중첩 표현이 Graphviz cluster가 더 정교해서 이쪽으로 결정."""

import subprocess

from django.db.models import Prefetch
from django.urls import reverse

from network.models import ServiceNetworkBackend, ServiceNetworkMapping
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


def collect_service_resources(service) -> dict:
    """서비스 하나에 걸린 실제 리소스(WEB vhost/WAS 컨테이너/DB 인스턴스/네트워크 매핑)를
    한 번만 모아서 돌려준다 - build_service_topology_graph(그래프)와
    build_service_resource_table(표) 둘 다 이 결과를 그대로 써서 같은 트래버설 로직
    (WebToB<->JEUS 커넥터, JEUS<->DB 데이터소스 등)이 두 군데서 중복되지 않는다. 여기서
    쿼리만 모으고 dot 텍스트/화면용 행 만들기는 각 소비 함수가 담당한다."""
    webtob_vhosts = list(WebtobVhost.objects.filter(service=service).select_related("source__asset"))
    apache_vhosts = list(ApacheVhost.objects.filter(service=service).select_related("source__asset"))
    nginx_vhosts = list(NginxVhost.objects.filter(service=service).select_related("source__asset"))
    containers = list(JeusContainer.objects.filter(service=service).select_related("asset", "source"))
    container_ids = {c.id for c in containers}

    connectors = []
    if webtob_vhosts and container_ids:
        connectors = list(
            JeusWebtobConnector.objects.filter(
                webtob_server__svrgroup__vhosts__in=webtob_vhosts,
                container_id__in=container_ids,
            )
            .select_related("container")
            .prefetch_related("webtob_server__svrgroup__vhosts")
            .distinct()
        )

    data_sources = []
    if container_ids:
        # 이 서비스의 WAS 컨테이너가 참조하는 데이터소스 중 DB 쪽 매칭(db_instance)이 실제로
        # 된 것만 - JeusDataSource.db_instance가 was/sync.py에서 push 시점에 이미 해석해둔
        # 값을 그대로 따라간다(여기서 새로 매칭하지 않음).
        data_sources = list(
            JeusDataSource.objects.filter(containers__id__in=container_ids, db_instance__isnull=False)
            .select_related("db_instance__source", "db_instance__asset")
            .prefetch_related("containers")
            # containers__id__in이 M2M(to-many) 조인이라 .distinct()가 실제로 필요한데,
            # select_related로 끌려온 DbInstance.extra/DbConfigSource.raw_content·extra가
            # Oracle NCLOB이라 DISTINCT 대상에 섞이면 ORA-00932가 난다(CLAUDE.md 환경 섹션
            # 참고) - 이 화면에서 안 쓰는 값이라 defer로 SELECT에서 뺀다.
            .defer("db_instance__extra", "db_instance__source__raw_content", "db_instance__source__extra")
            .distinct()
        )

    # Apache/Nginx는 WebToB-JEUS와 달리 설정 내용에 뒷단 실서버 정보가 전혀 없어(VIP/도메인
    # 하나로만 지정하는 이중화 구성) network.ServiceNetworkMapping(사람이 등록)이 유일한 출처.
    # 서비스 하나에 홉(hop)이 여러 개일 수 있어(WEB->GW->WAS처럼 VIP를 두 번 거치는 구성,
    # ServiceNetworkMapping 모델 참고) hop_order 순으로 정렬된 리스트로 받는다 - 체인을 잇는
    # 쪽(build_service_topology_graph)이 순서를 그대로 신뢰한다.
    network_mappings = []
    if apache_vhosts or nginx_vhosts:
        network_mappings = list(
            ServiceNetworkMapping.objects.filter(service=service)
            .order_by("hop_order")
            .prefetch_related(Prefetch("backends", queryset=ServiceNetworkBackend.objects.select_related("asset")))
        )

    return {
        "webtob_vhosts": webtob_vhosts,
        "apache_vhosts": apache_vhosts,
        "nginx_vhosts": nginx_vhosts,
        "containers": containers,
        "container_ids": container_ids,
        "connectors": connectors,
        "data_sources": data_sources,
        "network_mappings": network_mappings,
    }


def build_service_resource_table(resources: dict) -> dict:
    """구성도 그래프 아래에 나열할 리소스 목록 - collect_service_resources 결과를 화면에
    바로 뿌리기 좋은 행 단위로 펼친다. 그래프가 "모양"을 보여준다면 이 표는 "목록"(검색/복사
    가능한 텍스트)을 보여주는 역할 - 같은 소스 데이터를 재사용하므로 그래프와 항상 일치한다.
    행마다 Asset(OS)/System 컬럼을 같이 넣어서 별도의 System/Asset 요약 표를 더 안 만들어도
    "이 WEB/WAS/DB가 어느 OS·물리 시스템에 있는지"까지 한 표에서 끝나게 한다."""
    web_rows = []
    for kind_label, vhosts in (
        ("WebToB", resources["webtob_vhosts"]),
        ("Apache", resources["apache_vhosts"]),
        ("Nginx", resources["nginx_vhosts"]),
    ):
        for vhost in vhosts:
            asset = vhost.source.asset
            web_rows.append(
                {
                    "kind": kind_label,
                    "name": vhost.name,
                    "endpoint": _vhost_endpoint_label(vhost),
                    "asset": asset,
                    "system": _system_host_for_asset(asset),
                    "detail_url": reverse("dashboard-webconfig-detail", args=[vhost.source_id]),
                }
            )

    was_rows = []
    for container in resources["containers"]:
        was_rows.append(
            {
                "kind": container.source.get_kind_display(),
                "name": container.name,
                "asset": container.asset,
                "system": _system_host_for_asset(container.asset),
                "detail_url": reverse("dashboard-was-detail", args=[container.source_id]),
            }
        )

    db_rows = []
    seen_instance_ids = set()
    container_ids = resources["container_ids"]
    for data_source in resources["data_sources"]:
        instance = data_source.db_instance
        if instance.id in seen_instance_ids:
            continue
        seen_instance_ids.add(instance.id)
        # 이 데이터소스를 참조하는 컨테이너 중 이 서비스에 속한 것만(M2M이라 다른 서비스의
        # 컨테이너도 같이 참조할 수 있음).
        via_names = [c.name for c in data_source.containers.all() if c.id in container_ids]
        db_rows.append(
            {
                "source_kind": instance.source.get_kind_display(),
                "db_unique_name": instance.source.db_unique_name,
                "instance_name": instance.instance_name,
                "via_containers": ", ".join(via_names),
                "asset": instance.asset,
                "system": _system_host_for_asset(instance.asset),
                "detail_url": reverse("dashboard-db-config-detail", args=[instance.source_id]),
            }
        )

    # hop_order 순서 그대로 - WEB->GW->WAS처럼 여러 홉이면 등록된 순서대로 나열해서 체인이
    # 눈으로 보이게 한다(그래프의 VIP 노드 체인과 항상 같은 순서).
    network_hop_rows = [
        {
            "label": mapping.label,
            "internal_vip": mapping.internal_vip,
            "external_domain": mapping.external_domain,
            "external_ip": mapping.external_ip,
            "backends": list(mapping.backends.all()),
        }
        for mapping in resources["network_mappings"]
    ]

    return {
        "web_rows": web_rows,
        "was_rows": was_rows,
        "db_rows": db_rows,
        "network_hop_rows": network_hop_rows,
    }


def build_service_topology_graph(resources: dict) -> dict:
    """collect_service_resources 결과를 받아 WEB vhost/WAS 컨테이너를 노드로, WebToB<->JEUS
    실제 연결(JeusWebtobConnector)과 JEUS<->DB 실제 연결(JeusDataSource.db_instance)만
    엣지로 만든다. 같은 asset을 가리키는 노드는 나중에 render_topology_svg에서 OS 클러스터
    하나로 자동 합쳐진다 - 여기서는 각 노드가 자기 asset을 들고 있기만 하면 된다.

    DB는 WEB/WAS와 달리 서비스가 직접 배정되는 대상이 아니라서(서비스는 vhost/컨테이너에만
    배정) DB 노드는 이 그래프에 이미 들어간 WAS 컨테이너가 참조하는 데이터소스를 따라가서
    간접적으로만 편입된다 - "이 서비스가 쓰는 DB"가 아니라 "이 서비스의 WAS 컨테이너가
    실제로 붙는 DB"라는 뜻이라 WebToB<->JEUS 엣지와 성격이 같다(둘 다 실제 연결을 따라가는
    것이지 서비스 배정을 따라가는 게 아님)."""
    webtob_vhosts = resources["webtob_vhosts"]
    apache_vhosts = resources["apache_vhosts"]
    nginx_vhosts = resources["nginx_vhosts"]
    containers = resources["containers"]
    container_ids = resources["container_ids"]

    nodes = []
    web_node_id_by_vhost = {}
    proxy_web_node_ids = []  # apache/nginx는 webtob-connector가 없어 VIP 매핑 엣지 대상
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
            else:
                proxy_web_node_ids.append(node_id)

    was_node_id_by_container = {}
    was_node_id_by_asset = {}
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
        if container.asset_id is not None:
            # 같은 asset에 컨테이너가 여러 개면 첫 번째만 - VIP 매핑 엣지는 "이 실서버 즈음"을
            # 보여주는 용도라 완전한 목록보다 간단한 매칭 하나로 충분(_system_host_for_asset와
            # 같은 원칙).
            was_node_id_by_asset.setdefault(container.asset_id, node_id)

    edges = []
    if webtob_vhosts:
        for connector in resources["connectors"]:
            to_id = was_node_id_by_container[connector.container_id]
            for vhost in connector.webtob_server.svrgroup.vhosts.all():
                from_id = web_node_id_by_vhost.get(vhost.id)
                if from_id is not None:
                    edges.append(
                        {"from": from_id, "to": to_id, "label": connector.name or connector.registration_id}
                    )

    if container_ids:
        # 같은 DbInstance를 여러 컨테이너가 공유할 수 있어 노드는 instance당 하나만 만들고
        # 엣지만 컨테이너 수만큼 추가한다.
        db_node_id_by_instance = {}
        for data_source in resources["data_sources"]:
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

    # Apache/Nginx는 WebToB-JEUS와 달리 설정 내용에 뒷단 실서버 정보가 전혀 없다(VIP/도메인
    # 하나로만 지정하는 이중화 구성) - 사람이 "네트워크" 탭에서 직접 등록한
    # network.ServiceNetworkMapping이 유일한 출처다. 확인된 연결(webtob-connector, db_instance)
    # 과 구분되게 점선으로 그려서 "실제 파싱된 연결"과 "사람이 등록한 추정 연결"을 섞어보이지
    # 않게 한다. 서비스 하나에 홉(hop)이 여러 개일 수 있어(WEB->GW->WAS, ServiceNetworkMapping
    # 모델 참고) hop_order 순서대로 VIP 노드를 체인으로 잇는다 - hop 0의 "from"은 WEB vhost
    # 노드, hop N(N>0)의 "from"은 hop N-1의 VIP 노드. 중간 hop(예: GW)의 실서버는 CMDB가 안
    # 쫓는 장비일 수 있어 개별 노드로는 안 그린다(전체 목록은 build_service_resource_table의
    # network_hop_rows에서 hop마다 전부 나열).
    if proxy_web_node_ids:
        network_mappings = resources["network_mappings"]
        previous_node_ids = proxy_web_node_ids
        # 마지막 hop의 실서버 중 WAS 컨테이너로 안 잡힌 asset(예: Apache가 도메인을 받아
        # VIP로 Tomcat에 넘기는 흔한 구성 - Tomcat은 이 CMDB가 아직 WAS 종류로 추적하지
        # 않아 JeusContainer가 없음)도 facts push로 asset 자체는 이미 알고 있으니, 그 asset만
        # 가리키는 OS 박스를 새로 만들어서 체인이 VIP에서 끊기지 않게 한다. 같은 asset을
        # 다른 backend가 또 가리켜도 노드가 중복 안 되게 asset_id 기준으로 캐시.
        backend_asset_node_id_by_asset = {}
        for index, mapping in enumerate(network_mappings):
            vip_label_lines = [mapping.label or "VIP"]
            if mapping.internal_vip:
                vip_label_lines.append(mapping.internal_vip)
            if mapping.external_domain:
                vip_label_lines.append(mapping.external_domain)
            vip_node_id = f"vip_{mapping.pk}"
            nodes.append(
                {
                    "id": vip_node_id,
                    "label": "\n".join(vip_label_lines),
                    "kind": "network",
                    "asset": None,
                    "detail_url": None,
                }
            )
            for from_id in previous_node_ids:
                edges.append({"from": from_id, "to": vip_node_id, "label": "VIP", "style": "dashed"})

            if index == len(network_mappings) - 1:
                target_ids = []
                for backend in mapping.backends.all():
                    if backend.asset_id is None:
                        continue
                    target_id = was_node_id_by_asset.get(backend.asset_id)
                    if target_id is None:
                        target_id = backend_asset_node_id_by_asset.get(backend.asset_id)
                        if target_id is None:
                            target_id = f"netbackend_{backend.asset_id}"
                            backend_asset_node_id_by_asset[backend.asset_id] = target_id
                            nodes.append(
                                {
                                    "id": target_id,
                                    "label": backend.asset.hostname,
                                    "asset": backend.asset,
                                    "detail_url": reverse("dashboard-asset-detail", args=[backend.asset_id]),
                                }
                            )
                    if target_id not in target_ids:
                        target_ids.append(target_id)
                for to_id in target_ids:
                    edges.append({"from": vip_node_id, "to": to_id, "label": "", "style": "dashed"})
                previous_node_ids = []
            else:
                previous_node_ids = [vip_node_id]

    return {"nodes": nodes, "edges": edges}


def _dot_escape(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_topology_svg(graph: dict) -> str:
    """build_service_topology_graph 결과를 dot 텍스트로 바꿔 graphviz(dot 바이너리, 이미지에
    apt로 설치됨)로 SVG를 렌더링한다. 노드는 asset(OS) -> 그 asset의 물리호스트(System)
    순으로 묶어 중첩 cluster로 만든다 - 같은 asset을 쓰는 노드가 여러 개면 자연히 한
    OS 박스 안에 같이 들어간다(예: 같은 서버에 WebToB/JEUS가 같이 뜬 경우)."""
    by_system: dict = {}
    network_nodes = []  # VIP 등 asset(OS)에 속하지 않는 노드는 클러스터 밖에 독립 도형으로
    for node in graph["nodes"]:
        if node.get("kind") == "network":
            network_nodes.append(node)
            continue
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

    for node in network_nodes:
        # VIP는 실제 OS 박스가 아니라 사람이 등록한 네트워크 주소 개념이라 System/OS 클러스터에
        # 넣지 않고 마름모(diamond)로 독립 표시 - 다른 노드(box)와 형태부터 다르게 구분.
        lines.append(
            f'  {node["id"]} [label={_dot_escape(node["label"])}, shape=diamond, '
            'fillcolor="#fff8e1", color="#e0c46c"];'
        )

    for edge in graph["edges"]:
        style_attr = f', style={_dot_escape(edge["style"])}' if edge.get("style") else ""
        lines.append(
            f'  {edge["from"]} -> {edge["to"]} [label={_dot_escape(edge["label"] or "")}{style_attr}];'
        )

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
