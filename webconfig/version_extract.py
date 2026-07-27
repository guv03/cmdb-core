import re

# AWX가 push할 원본 맨 위에 얹어 보내는 마커 한 줄. WebtoB 파서(webconfig/parsers.py)는
# '#'로 시작하는 줄을 그냥 주석으로 버려서 이 마커가 있어도 설정 파싱엔 영향이 없다.
_MARKER_RE = re.compile(r"^#\s*CMDB_SOLUTION_VERSION:\s*(.+)$", re.MULTILINE)
# wsadmin -version 출력 형식: "WebtoB 5.0 SP 0 Fix #4 Linux-K2.6_x64 FD16384 B404 epoll 2026/05/19"
_WEBTOB_VERSION_RE = re.compile(r"^WebtoB\s+(?P<version>\S+)\s+(?P<fix>.+)$")


def extract_webtob_version(content: str) -> tuple[str, str] | None:
    """push된 원본 텍스트에서 CMDB_SOLUTION_VERSION 마커를 찾아 (버전, Fix)로 나눈다.
    마커 자체가 없으면 None을 반환 - 호출부는 이 경우 기존 값을 그대로 둬야 한다(아직
    마커를 안 보내는 자산의 값이 push 때마다 사라지면 안 되므로). 마커는 있는데
    "WebtoB <버전> <나머지>" 형식이 아니면 전체를 버전에 넣고 Fix는 빈 문자열로 둔다."""
    marker_match = _MARKER_RE.search(content)
    if marker_match is None:
        return None

    raw_version = marker_match.group(1).strip()
    version_match = _WEBTOB_VERSION_RE.match(raw_version)
    if version_match is None:
        return raw_version, ""
    return version_match.group("version"), version_match.group("fix").strip()


VERSION_EXTRACTORS = {"webtob": extract_webtob_version}
