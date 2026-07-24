import re


def _strip_comment(line: str) -> str:
    """따옴표 밖의 '#'부터 줄 끝까지 주석으로 간주해 잘라낸다."""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "#" and not in_quotes:
            return line[:i]
    return line


def _split_attrs(text: str) -> dict:
    """'KEY1 = "a,b", KEY2 = val' 형태를 따옴표 안의 콤마는 무시하며 파싱. 키는 소문자로 정규화."""
    parts = []
    current = []
    in_quotes = False
    for ch in text:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))

    attrs = {}
    for part in parts:
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        attrs[key] = value
    return attrs


_ENTRY_RE = re.compile(r"^(\S+)\s*(.*)$")


def parse_webtob(content: str) -> dict:
    """WebtoB http.m 텍스트를 {섹션명: {엔트리명: {키: 값}}}으로 변환.
    *DOMAIN만 예외로 {"DOMAIN": "<값>"}(엔트리 없는 단일 값)."""
    sections: dict = {}
    current_section = None
    current_entry_name = None
    current_entry_text: list[str] = []
    domain_value = None

    def flush_entry():
        nonlocal current_entry_name, current_entry_text
        if current_section is not None and current_entry_name is not None:
            attrs = _split_attrs(" ".join(current_entry_text))
            sections.setdefault(current_section, {})[current_entry_name] = attrs
        current_entry_name = None
        current_entry_text = []

    for raw_line in content.splitlines():
        line = _strip_comment(raw_line)
        if not line.strip():
            continue

        stripped = line.lstrip()
        is_indented = line != stripped

        if stripped.startswith("*"):
            flush_entry()
            current_section = stripped[1:].strip().upper()
            continue

        if current_section == "DOMAIN" and domain_value is None and not is_indented:
            domain_value = stripped.strip()
            continue

        if is_indented and current_entry_name is not None:
            current_entry_text.append(stripped)
            continue

        flush_entry()
        match = _ENTRY_RE.match(stripped)
        if not match:
            continue
        current_entry_name = match.group(1)
        current_entry_text = [match.group(2)] if match.group(2) else []

    flush_entry()

    if domain_value is not None:
        sections["DOMAIN"] = domain_value

    return sections


PARSERS = {"webtob": parse_webtob}
