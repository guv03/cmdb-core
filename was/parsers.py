import re
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


def _parse_data_source_names(server_elem: ET.Element) -> list[str]:
    """<server>의 <data-sources><data-source>이름</data-source>... - 콤마로 여러 개를 한 번에
    지정하는 WebToB의 VhostName과 달리 태그가 반복되는 형태라 findall로 바로 리스트를 만든다."""
    return [
        elem.text.strip()
        for elem in server_elem.findall("data-sources/data-source")
        if elem.text and elem.text.strip()
    ]


def _parse_data_sources(root: ET.Element) -> list[dict]:
    """<resources><data-source><database> - 도메인 레벨 JDBC 커넥션 풀 정의. 특정 컨테이너에
    속하지 않고 컨테이너 쪽에서 data_source_id로 이름 참조한다(_parse_data_source_names).
    password는 암호화돼 있어도 민감정보라 아예 안 뽑는다."""
    data_sources = []
    for ds_elem in root.findall("resources/data-source"):
        db = ds_elem.find("database")
        if db is None:
            continue
        data_sources.append(
            {
                "data_source_id": _text(db, "data-source-id"),
                "export_name": _text(db, "export-name"),
                "vendor": _text(db, "vendor"),
                "db_host": _text(db, "server-name"),
                "port": _text(db, "port-number"),
                "database_name": _text(db, "database-name"),
                "db_user": _text(db, "user"),
                "pool_min": _text(db, "connection-pool/pooling/min"),
                "pool_max": _text(db, "connection-pool/pooling/max"),
            }
        )
    return data_sources


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


def parse_jeus(content: str) -> dict:
    """JEUS(7/8/8.5/9 - domain.xml 레이아웃 공통) domain.xml을 {"admin_server_name",
    "domain_version", "containers": [...], "data_sources": [...]}로 변환. 컨테이너(<server>)
    하나당 name/node_name/listen_port/ssl_port/deployed_apps_summary/webtob_connectors/
    data_source_names(이 컨테이너가 참조하는 도메인 레벨 data_source_id 목록)를 담는다."""
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
                "data_source_names": _parse_data_source_names(server_elem),
            }
        )

    return {
        "admin_server_name": admin_server_name,
        "domain_version": domain_version,
        "containers": containers,
        "data_sources": _parse_data_sources(root),
    }


def _parse_jeus6_webtob_listeners(content: str) -> list[dict]:
    """servlet_engine{N}/WEBMain.xml의 <webtob-listener> - JEUS(7+) domain.xml의
    <webtob-connector>에 대응하는 컨테이너별 웹 커넥션 정보. wjp-version 개념은 JEUS6에
    없어 빈 문자열로 둔다(JeusWebtobConnector 필드 자체는 kind 공용이라 그대로 재사용)."""
    root = ET.fromstring(content)
    _strip_namespace(root)
    connectors = []
    for listener in root.findall("context-group/webserver-connection/webtob-listener"):
        connectors.append(
            {
                "name": _text(listener, "listener-id"),
                "registration_id": _text(listener, "registration-id"),
                "network_address": _text(listener, "webtob-address"),
                "port": _text(listener, "port"),
                "wjp_version": "",
            }
        )
    return connectors


def _parse_jeus6_data_sources(root: ET.Element) -> list[dict]:
    """<resource><data-source><database> - JEUS(7+)의 <resources><data-source>와 같은
    도메인 레벨 JDBC 커넥션 풀 정의지만, JEUS6엔 data-source-id가 따로 없어 유일한
    식별자인 export-name을 data_source_id로 쓴다. 어떤 컨테이너가 쓰는지 참조하는 요소가
    파일에 아예 없어(JEUS6 리소스는 노드 전체 암묵적 공용) 컨테이너 연결은 parse_jeus6가
    이 노드의 모든 컨테이너에 일괄로 채운다."""
    data_sources = []
    for db in root.findall("resource/data-source/database"):
        data_sources.append(
            {
                "data_source_id": _text(db, "export-name"),
                "export_name": _text(db, "export-name"),
                "vendor": _text(db, "vendor"),
                "db_host": _text(db, "server-name"),
                "port": _text(db, "port-number"),
                "database_name": _text(db, "database-name"),
                "db_user": _text(db, "user"),
                "pool_min": _text(db, "connection-pool/pooling/min"),
                "pool_max": _text(db, "connection-pool/pooling/max"),
            }
        )
    return data_sources


def parse_jeus6(files: dict[str, str]) -> dict:
    """JEUS6(JEUSMain.xml + 컨테이너별 servlet_engine{N}/WEBMain.xml)을 parse_jeus와 같은
    반환 형태({"admin_server_name", "domain_version", "containers": [...],
    "data_sources": [...]}, 추가로 "node_name")로 변환 - was/sync.py가 kind 무관하게 같은
    구조로 처리할 수 있게 맞춘다.

    JEUSMain.xml 하나 = 물리 노드 하나(도메인 전체를 담는 domain.xml과 달리 admin 서버
    개념이 없음)라는 전제라 admin_server_name은 항상 빈 문자열, hostname 판별은
    was/views.py가 최상위 node_name을 직접 쓴다.

    <application>의 <engine-container-name>은 "{node명}_{container명}" 합성 키라 접두사를
    떼어 컨테이너 이름만 남긴다. servlet_engine{N}/WEBMain.xml 매칭은 <engine-command>
    <name>engine{N}</engine-command>의 숫자로 하는데(폴더명 자체가 항상 이 규칙을 따름 -
    컨테이너 이름이 아니라 엔진 이름 기준이라는 점에 주의), 해당 파일이 payload에 없으면
    (엔진 전용/웹 커넥션 없는 컨테이너) webtob_connectors는 빈 리스트로 둔다."""
    jeus_main = files.get("JEUSMain.xml", "")
    root = ET.fromstring(jeus_main)
    _strip_namespace(root)

    domain_version = root.get("version", "")
    node_elem = root.find("node")
    node_name = _text(node_elem, "name") if node_elem is not None else ""

    # <application>은 "{node명}_{container명}" 합성 키로 컨테이너를 참조한다.
    apps_by_container: dict[str, list[str]] = {}
    for app in root.findall("application"):
        target_key = _text(app, "deployment-target/target/engine-container-name")
        prefix = f"{node_name}_"
        container_name = target_key[len(prefix) :] if node_name and target_key.startswith(prefix) else target_key
        if not container_name:
            continue
        app_path = _text(app, "path")
        app_name = _text(app, "name")
        label = f"{app_path} ({app_name})" if app_name else app_path
        apps_by_container.setdefault(container_name, []).append(label)

    data_sources = _parse_jeus6_data_sources(root)
    all_ds_ids = [ds["data_source_id"] for ds in data_sources if ds["data_source_id"]]

    containers = []
    for server_elem in node_elem.findall("engine-container") if node_elem is not None else []:
        name = _text(server_elem, "name")
        engine_name = _text(server_elem, "engine-command/name")

        webtob_connectors = []
        engine_num = re.search(r"(\d+)\s*$", engine_name)
        if engine_num:
            web_main_content = files.get(f"servlet_engine{engine_num.group(1)}/WEBMain.xml")
            if web_main_content:
                webtob_connectors = _parse_jeus6_webtob_listeners(web_main_content)

        containers.append(
            {
                "name": name,
                "node_name": node_name,
                "listen_port": "",
                "ssl_port": "",
                "deployed_apps_summary": ", ".join(apps_by_container.get(name, [])),
                "webtob_connectors": webtob_connectors,
                # 컨테이너별 참조가 없어(위 docstring 참고) 이 노드의 모든 컨테이너에 일괄 연결.
                "data_source_names": list(all_ds_ids),
            }
        )

    return {
        "admin_server_name": "",
        "node_name": node_name,
        "domain_version": domain_version,
        "containers": containers,
        "data_sources": data_sources,
    }


_ORACLE_LONG_URL_RE = re.compile(
    r"HOST\s*=\s*([^)\s]+).*?PORT\s*=\s*(\d+).*?SERVICE_NAME\s*=\s*([^)\s]+)",
    re.IGNORECASE | re.DOTALL,
)
_ORACLE_SHORT_URL_RE = re.compile(r"@([^:/]+):(\d+)[:/]([^\s?]+)", re.IGNORECASE)


def _parse_oracle_jdbc_url(url: str) -> tuple[str, str, str]:
    """Oracle thin JDBC 커넥트 문자열에서 (host, port, service_name/SID)를 뽑는다 - JEUS의
    <database-name> 프로퍼티처럼 이미 분리된 값이 아니라 문자열 하나로 되어 있어 정규식으로
    파싱해야 한다. 긴 형식(DESCRIPTION=(ADDRESS=...)(CONNECT_DATA=(SERVICE_NAME=...)))을 먼저
    시도하고, 안 맞으면 짧은 형식(@host:port:sid 또는 @host:port/service)을 시도한다. 뽑아낸
    값은 JEUS와 동일하게 database_name 필드에 담겨 DbInstance.instance_name과 매칭된다
    (was/sync.py의 _resolve_db_instance) - db_host는 매칭에 안 쓰는 것도 동일(RAC VIP/SCAN
    문제, CLAUDE.md "데이터베이스" 섹션 참고)."""
    if not url:
        return "", "", ""
    match = _ORACLE_LONG_URL_RE.search(url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    match = _ORACLE_SHORT_URL_RE.search(url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return "", "", ""


def _vendor_from_driver_class(driver_class_name: str) -> str:
    if "oracle" in driver_class_name.lower():
        return "oracle"
    return driver_class_name


def _parse_tomcat_datasources(context_root: ET.Element | None) -> list[dict]:
    """context.xml(보통 $CATALINA_BASE/conf/context.xml - 이 인스턴스의 모든 웹앱에 공유되는
    전역 설정)의 <Resource type="javax.sql.DataSource"> - JEUS의 <resources><data-source>와
    같은 도메인(여기서는 인스턴스) 레벨 JDBC 커넥션 풀 정의다. Tomcat엔 컨테이너별로 어떤
    데이터소스를 쓰는지 명시하는 참조 요소 자체가 없어(JEUS6과 동일한 상황 - 리소스가 인스턴스
    전체에 암묵적으로 공용) parse_tomcat이 이 인스턴스의 모든 컨테이너에 일괄 연결한다.
    password는 설정에 암호화된 값으로 있어도 민감정보라 JEUS와 동일하게 아예 안 뽑는다."""
    if context_root is None:
        return []
    data_sources = []
    for resource in context_root.findall(".//Resource"):
        if resource.get("type") != "javax.sql.DataSource":
            continue
        name = resource.get("name", "")
        if not name:
            continue
        host, port, database_name = _parse_oracle_jdbc_url(resource.get("url", ""))
        data_sources.append(
            {
                "data_source_id": name,
                "export_name": name,
                "vendor": _vendor_from_driver_class(resource.get("driverClassName", "")),
                "db_host": host,
                "port": port,
                "database_name": database_name,
                "db_user": resource.get("username", ""),
                "pool_min": resource.get("minIdle", ""),
                "pool_max": resource.get("maxActive", ""),
            }
        )
    return data_sources


def _parse_tomcat_connectors(service_elem: ET.Element) -> tuple[str, str]:
    """<Connector port="..." protocol="HTTP/1.1" .../> - SSLEnabled="true"인 첫 커넥터를
    ssl_port로, 아닌 첫 커넥터를 listen_port로 잡는다 - JEUS의 <listeners><listener>
    (BASE/SSL 구분)와 같은 역할."""
    listen_port = ""
    ssl_port = ""
    for connector in service_elem.findall("Connector"):
        port = connector.get("port", "")
        if connector.get("SSLEnabled", "").lower() == "true":
            ssl_port = ssl_port or port
        else:
            listen_port = listen_port or port
    return listen_port, ssl_port


def _parse_tomcat_deployed_apps(service_elem: ET.Element) -> str:
    """<Engine><Host name="..."><Context path="..." docBase="..."/> - 배포된 웹앱을
    "호스트: path(docBase)" 형태로 콤마 이어붙인다(JEUS의 deployed_apps_summary와 같은 역할).
    path=""는 ROOT 컨텍스트(URL 루트)를 뜻해 사람이 읽기 좋게 "ROOT"로 표시."""
    labels = []
    for host_elem in service_elem.findall("Engine/Host"):
        host_name = host_elem.get("name", "")
        for context_elem in host_elem.findall("Context"):
            path = context_elem.get("path", "") or "ROOT"
            doc_base = context_elem.get("docBase", "")
            label = f"{path} ({doc_base})" if doc_base else path
            labels.append(f"{host_name}: {label}" if host_name else label)
    return ", ".join(labels)


def parse_tomcat(files: dict[str, str], hostname: str) -> dict:
    """Tomcat(server.xml [+ context.xml])을 parse_jeus와 같은 반환 형태({"admin_server_name",
    "domain_version", "containers": [...], "data_sources": [...]})로 변환해 was/sync.py의
    sync_jeus를 그대로 재사용한다(JEUS6과 동일 전략 - kind별 동기화 로직 분기가 필요 없음).

    JEUS의 domain.xml과 달리 server.xml엔 자기 자신을 가리키는 hostname 정보가 전혀 없다
    (Apache/Nginx의 ServerName 부재와 같은 이유) - 그래서 was/views.py가 apache/nginx와 동일
    패턴으로 AWX 페이로드의 hostname 필드를 받아 이 함수에 그대로 넘겨주고, 여기서 모든
    컨테이너의 node_name에 그 값을 채운다(sync_was_containers의 _resolve_asset이 node_name으로
    asset을 찾으므로 - was/models.py의 kind 주석 참고). admin_server_name은 JEUS6과 동일하게
    항상 빈 문자열(admin 서버 개념 자체가 없음).

    <Service> 하나 = 컨테이너(WasContainer) 하나 - 인스턴스 하나(server.xml 하나)에 보통
    <Service>가 하나뿐이지만 이론상 여러 개도 지원한다. webtob_connectors는 항상 빈 리스트
    (Tomcat은 WebToB에 등록되는 개념이 없음 - Apache가 VIP로 바로 프록시하는 구성은
    network.NetworkRoute가 다룸, CLAUDE.md "구성도" 섹션 참고). 데이터소스는
    JEUS6과 동일 원칙으로 이 인스턴스의 모든 컨테이너에 일괄 연결한다."""
    server_content = files.get("server.xml", "")
    if not server_content:
        return {
            "admin_server_name": "",
            "node_name": hostname,
            "domain_version": "",
            "containers": [],
            "data_sources": [],
        }

    root = ET.fromstring(server_content)

    context_content = files.get("context.xml", "")
    context_root = ET.fromstring(context_content) if context_content else None
    data_sources = _parse_tomcat_datasources(context_root)
    all_ds_ids = [ds["data_source_id"] for ds in data_sources if ds["data_source_id"]]

    containers = []
    for service_elem in root.findall("Service"):
        name = service_elem.get("name", "")
        listen_port, ssl_port = _parse_tomcat_connectors(service_elem)

        containers.append(
            {
                "name": name,
                "node_name": hostname,
                "listen_port": listen_port,
                "ssl_port": ssl_port,
                "deployed_apps_summary": _parse_tomcat_deployed_apps(service_elem),
                "webtob_connectors": [],
                "data_source_names": list(all_ds_ids),
            }
        )

    return {
        "admin_server_name": "",
        "node_name": hostname,
        "domain_version": "",
        "containers": containers,
        "data_sources": data_sources,
    }


PARSERS = {"jeus": parse_jeus, "jeus6": parse_jeus6, "tomcat": parse_tomcat}
