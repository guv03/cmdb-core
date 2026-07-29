import re

# AWX가 push할 원본 맨 위에 얹어 보내는 마커 한 줄. kind별 파서(webconfig/parsers.py)는
# '#'로 시작하는 줄을 그냥 주석으로 버려서(또는 애초에 파싱 대상 블록 밖이라) 이 마커가
# 있어도 설정 파싱엔 영향이 없다.
_MARKER_RE = re.compile(r"^#\s*CMDB_SOLUTION_VERSION:\s*(.+)$", re.MULTILINE)
# wsadmin -version 출력 형식: "WebtoB 5.0 SP 0 Fix #4 Linux-K2.6_x64 FD16384 B404 epoll 2026/05/19"
_WEBTOB_VERSION_RE = re.compile(r"^WebtoB\s+(?P<version>\S+)\s+(?P<fix>.+)$")
# apachectl -version 첫 줄 형식: "Server version: Apache/2.4.51 (Unix)"
_APACHE_VERSION_RE = re.compile(r"^Server version:\s*(?P<version>.+)$", re.IGNORECASE)
# nginx -v 출력 형식(stderr로 나감): "nginx version: nginx/1.24.0"
_NGINX_VERSION_RE = re.compile(r"^nginx version:\s*(?P<version>.+)$", re.IGNORECASE)


def _extract_marker_value(content: str) -> str | None:
    """CMDB_SOLUTION_VERSION 마커 줄의 값을 꺼낸다. 마커 자체가 없으면 None."""
    marker_match = _MARKER_RE.search(content)
    if marker_match is None:
        return None

    raw_value = marker_match.group(1).strip()
    # 방어 코드: 마커 줄과 실제 설정 내용 사이의 구분자가 실제 개행이 아니라 리터럴 "\n"(백슬래시+n
    # 두 글자)로 들어온 사례가 있었다(AWX 쪽 Jinja/YAML 이스케이프 처리 이슈, awx/push_webtob_config_to_cmdb.yml
    # 참고). 정규식(위 _MARKER_RE)은 실제 개행에서만 멈추므로 이 경우 다음 섹션 내용까지 그대로
    # 캡처해버려 값이 오염된다 - 리터럴 "\n"이 보이면 그 이후는 버린다.
    return raw_value.split("\\n", 1)[0].strip()


def extract_webtob_version(content: str) -> tuple[str, str] | None:
    """push된 원본 텍스트에서 CMDB_SOLUTION_VERSION 마커를 찾아 (버전, Fix)로 나눈다.
    마커 자체가 없으면 None을 반환 - 호출부는 이 경우 기존 값을 그대로 둬야 한다(아직
    마커를 안 보내는 자산의 값이 push 때마다 사라지면 안 되므로). 마커는 있는데
    "WebtoB <버전> <나머지>" 형식이 아니면 전체를 버전에 넣고 Fix는 빈 문자열로 둔다."""
    raw_version = _extract_marker_value(content)
    if raw_version is None:
        return None

    version_match = _WEBTOB_VERSION_RE.match(raw_version)
    if version_match is None:
        return raw_version, ""
    return version_match.group("version"), version_match.group("fix").strip()


def extract_apache_version(content: str) -> tuple[str, str] | None:
    """apachectl -version 출력 첫 줄("Server version: ..." 부분)만 마커로 받아 버전으로
    쓴다(두 번째 줄 Server built는 AWX 플레이북에서 애초에 안 보냄). WebToB와 달리 Fix
    개념이 없어 두 번째 값은 항상 빈 문자열."""
    raw_version = _extract_marker_value(content)
    if raw_version is None:
        return None

    version_match = _APACHE_VERSION_RE.match(raw_version)
    if version_match is None:
        return raw_version, ""
    return version_match.group("version").strip(), ""


def extract_nginx_version(content: str) -> tuple[str, str] | None:
    """nginx -v 출력("nginx version: ..." 부분)을 마커로 받아 버전으로 쓴다. Fix 개념 없음."""
    raw_version = _extract_marker_value(content)
    if raw_version is None:
        return None

    version_match = _NGINX_VERSION_RE.match(raw_version)
    if version_match is None:
        return raw_version, ""
    return version_match.group("version").strip(), ""


VERSION_EXTRACTORS = {
    "webtob": extract_webtob_version,
    "apache": extract_apache_version,
    "nginx": extract_nginx_version,
}
