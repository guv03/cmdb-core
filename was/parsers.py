import xml.etree.ElementTree as ET


def _strip_namespace(root: ET.Element) -> None:
    """domain.xml의 기본 네임스페이스(xmlns=".../ns/jeus") 때문에 태그가 전부
    "{ns}tagname" 형태가 되는데, 매 find()마다 네임스페이스를 신경 쓰지 않도록 파싱
    직후 모든 엘리먼트의 태그에서 "{...}" 접두사를 제거한다. JEUS 버전마다 네임스페이스
    문자열이 달라져도(버전 속성과 무관) 영향받지 않게 하기 위함."""
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]


def _text(elem: ET.Element | None, path: str, default: str = "") -> str:
    if elem is None:
        return default
    found = elem.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _parse_webtob_connectors(server_elem: ET.Element) -> list[dict]:
    connectors = []
    for connector in server_elem.findall("web-engine/web-connections/webtob-connector"):
        connectors.append(
            {
                "name": _text(connector, "name"),
                "registration_id": _text(connector, "registration-id"),
                "network_address": _text(connector, "network-address/ip-address"),
                "port": _text(connector, "network-address/port"),
                "wjp_version": _text(connector, "wjp-version"),
            }
        )
    return connectors


def _parse_listeners(server_elem: ET.Element) -> tuple[str, str]:
    """(BASE 리스너 포트, SSL 리스너 포트)를 반환. SSL 리스너가 없으면 두 번째 값은 빈 문자열."""
    listen_port = ""
    ssl_port = ""
    for listener in server_elem.findall("listeners/listener"):
        name = _text(listener, "name")
        port = _text(listener, "listen-port")
        if name == "BASE":
            listen_port = port
        if listener.find("ssl") is not None and not ssl_port:
            ssl_port = port
    return listen_port, ssl_port


def parse_jeus8(content: str) -> dict:
    """JEUS 8 domain.xml을 {"admin_server_name", "domain_version", "containers": [...]}로
    변환. 컨테이너(<server>) 하나당 name/node_name/listen_port/ssl_port/
    deployed_apps_summary/webtob_connectors를 담는다."""
    root = ET.fromstring(content)
    _strip_namespace(root)

    domain_version = root.get("version", "")
    admin_server_name = _text(root, "admin-server-name")

    # deployed-application은 target-server/name으로 컨테이너를 참조 - 서버 이름별로 모아둔다.
    # context-path는 배포 환경에 따라 대부분 "/"로만 찍혀 있어(URL 루트) 앱을 구분하는 데
    # 도움이 안 되고, 실제로 어떤 앱인지 구분되는 값은 배포 경로(path, 예: "/deploy/cmp")라
    # id와 함께 보여준다.
    apps_by_server: dict[str, list[str]] = {}
    for app in root.findall("deployed-applications/deployed-application"):
        server_name = _text(app, "target-server/name")
        if not server_name:
            continue
        app_path = _text(app, "path")
        app_id = _text(app, "id")
        label = f"{app_path} ({app_id})" if app_id else app_path
        apps_by_server.setdefault(server_name, []).append(label)

    containers = []
    for server_elem in root.findall("servers/server"):
        name = _text(server_elem, "name")
        node_name = _text(server_elem, "node-name")
        listen_port, ssl_port = _parse_listeners(server_elem)

        containers.append(
            {
                "name": name,
                "node_name": node_name,
                "listen_port": listen_port,
                "ssl_port": ssl_port,
                "deployed_apps_summary": ", ".join(apps_by_server.get(name, [])),
                "webtob_connectors": _parse_webtob_connectors(server_elem),
            }
        )

    return {
        "admin_server_name": admin_server_name,
        "domain_version": domain_version,
        "containers": containers,
    }


PARSERS = {"jeus8": parse_jeus8}
