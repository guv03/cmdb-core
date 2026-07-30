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


_VHOST_RE = re.compile(r"<VirtualHost\s+([^>]*)>(.*?)</VirtualHost>", re.IGNORECASE | re.DOTALL)
_DIRECTIVE_RE = re.compile(r"^(\w+)\s+(.*)$")


def _strip_directive_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return value


def _first_token(value: str) -> str:
    """공백으로 여러 인자를 받는 지시어(CustomLog "경로 옵션들" 포맷명 등)에서 첫 인자만
    뽑는다. 따옴표로 묶인 경로 안에 공백이 있을 수 있어(rotatelogs 파이프 명령 등) 단순
    split()으로는 못 자르고 따옴표를 먼저 확인한다."""
    value = value.strip()
    if value.startswith('"'):
        end = value.find('"', 1)
        if end != -1:
            return value[1:end]
    parts = value.split()
    return parts[0] if parts else ""


def _parse_global_ssl_defaults(content: str) -> tuple[str, str]:
    """(SSLProtocol, SSLCipherSuite) 전역 기본값 - 이 두 지시어는 mod_ssl 관례상 vhost마다
    안 적고 <VirtualHost> 밖(서버 전역 설정)에 한 번만 두는 경우가 흔하다(샘플
    httpd-ssl.conf도 그렇게 돼있음). vhost 블록 안에 있으면 아래 파싱 루프가 그 값으로
    덮어쓰므로, 여기서는 vhost에 값이 없을 때의 폴백만 구한다. VirtualHost 블록을 통째로
    지워서 전역 영역만 남긴 텍스트를 스캔한다."""
    global_content = _VHOST_RE.sub("", content)
    protocols = ""
    ciphers = ""
    for raw_line in global_content.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        match = _DIRECTIVE_RE.match(line)
        if not match:
            continue
        directive = match.group(1).lower()
        value = _strip_directive_value(match.group(2))
        if directive == "sslprotocol":
            protocols = value
        elif directive == "sslciphersuite":
            ciphers = value
    return protocols, ciphers


def parse_apache(content: str) -> dict:
    """httpd <VirtualHost ADDR:PORT> ... </VirtualHost> 블록을 vhost 목록으로 변환.
    WebToB처럼 이름으로 참조하는 절 구조가 아니라 블록 하나가 그대로 독립적인 값 뭉치라
    {SECTION: {...}}이 아니라 {"vhosts": [...]} 형태로 둔다."""
    global_ssl_protocols, global_ssl_ciphers = _parse_global_ssl_defaults(content)

    vhosts = []
    for addr_port_match, block in _VHOST_RE.findall(content):
        port = addr_port_match.rsplit(":", 1)[-1].strip() if ":" in addr_port_match else ""

        server_name = ""
        aliases: list[str] = []
        docroot = ""
        ssl_flag = False
        ssl_cert = ""
        ssl_key = ""
        ssl_protocols = ""
        ssl_ciphers = ""
        errorlog = ""
        logging = ""
        proxy_lines = []

        for raw_line in block.splitlines():
            line = _strip_comment(raw_line).strip()
            if not line:
                continue
            match = _DIRECTIVE_RE.match(line)
            if not match:
                continue
            directive = match.group(1).lower()
            value = _strip_directive_value(match.group(2))

            if directive == "servername":
                server_name = value.rsplit(":", 1)[0] if ":" in value else value
            elif directive == "serveralias":
                aliases.extend(v for v in value.split() if v)
            elif directive == "documentroot":
                docroot = value
            elif directive == "sslengine":
                ssl_flag = value.lower() == "on"
            elif directive == "sslcertificatefile":
                ssl_cert = value
            elif directive == "sslcertificatekeyfile":
                ssl_key = value
            elif directive == "sslprotocol":
                ssl_protocols = value
            elif directive == "sslciphersuite":
                ssl_ciphers = value
            elif directive == "errorlog":
                errorlog = value
            elif directive in ("customlog", "transferlog"):
                logging = _first_token(value)
            elif directive in ("proxypass", "proxypassmatch"):
                proxy_lines.append(value)

        vhosts.append(
            {
                "hostname": server_name,
                "hostalias": ", ".join(dict.fromkeys(aliases)),
                "port": port,
                "docroot": docroot,
                "ssl_flag": ssl_flag,
                "ssl_certificate_file": ssl_cert,
                "ssl_certificate_key_file": ssl_key,
                # vhost 안에 직접 없으면(흔한 경우) 전역 mod_ssl 설정으로 폴백 - SSL을 안 쓰는
                # vhost한테까지 전역값을 채우면 오해 소지가 있어 ssl_flag일 때만 채운다.
                "ssl_protocols": ssl_protocols or (global_ssl_protocols if ssl_flag else ""),
                "ssl_ciphers": ssl_ciphers or (global_ssl_ciphers if ssl_flag else ""),
                "logging": logging,
                "errorlog": errorlog,
                "proxy_summary": ", ".join(proxy_lines),
            }
        )

    return {"vhosts": vhosts}


def _split_nginx_blocks(text: str) -> list[tuple[str, str, str]]:
    """중괄호 깊이를 추적해 최상위 블록만 (지시어, 인자, 본문) 튜플로 뽑아낸다.
    nginx.conf는 http/events/server/location이 전부 중괄호 중첩이라 정규식만으론
    블록 경계를 못 잡아 직접 순회한다."""
    blocks = []
    i = 0
    n = len(text)
    while i < n:
        brace_idx = text.find("{", i)
        semi_idx = text.find(";", i)
        if brace_idx == -1:
            break
        if semi_idx != -1 and semi_idx < brace_idx:
            i = semi_idx + 1
            continue

        header = text[i:brace_idx].strip()
        parts = header.split(None, 1)
        directive = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        depth = 1
        j = brace_idx + 1
        while j < n and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[brace_idx + 1 : j - 1]

        if directive:
            blocks.append((directive, args, body))
        i = j
    return blocks


def _nginx_top_level_directives(body: str) -> list[tuple[str, str]]:
    """블록 본문에서 중첩 블록(location 등) 안은 건너뛰고 세미콜론으로 끝나는
    최상위 지시어만 (이름, 인자) 목록으로 뽑는다."""
    directives = []
    i = 0
    n = len(body)
    while i < n:
        semi_idx = body.find(";", i)
        brace_idx = body.find("{", i)
        if semi_idx == -1 and brace_idx == -1:
            break
        if brace_idx != -1 and (semi_idx == -1 or brace_idx < semi_idx):
            depth = 1
            j = brace_idx + 1
            while j < n and depth > 0:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                j += 1
            i = j
            continue

        line = _strip_comment(body[i:semi_idx]).strip()
        i = semi_idx + 1
        if not line:
            continue
        parts = line.split(None, 1)
        directives.append((parts[0].lower(), parts[1].strip() if len(parts) > 1 else ""))
    return directives


def parse_nginx(content: str) -> dict:
    """http { server { ... } } 구조에서 최상위 server 블록만 vhost로 뽑는다.
    블록 경계 탐지는 중괄호 문자만 보고 판단하므로, 주석으로 꺼놓은 서버 블록 안의
    '{'/'}'까지 진짜 블록으로 잘못 셀 수 있어 먼저 라인 단위로 주석을 지운다."""
    content = "\n".join(_strip_comment(line) for line in content.splitlines())
    vhosts = []
    for directive, _args, body in _split_nginx_blocks(content):
        if directive.lower() != "http":
            continue

        # ssl_protocols/ssl_ciphers는 server{} 블록마다 안 적고 http{} 최상위에 한 번만
        # 두는 경우도 흔해서(Apache의 전역 SSLProtocol/SSLCipherSuite와 같은 취지) 이 두
        # 값을 폴백으로 미리 구해둔다. _nginx_top_level_directives는 중첩 블록(server 등)
        # 안은 건너뛰므로 http{} 자기 자신의 최상위 지시어만 잡힌다.
        http_ssl_protocols = ""
        http_ssl_ciphers = ""
        for name, value in _nginx_top_level_directives(body):
            if name == "ssl_protocols":
                http_ssl_protocols = value
            elif name == "ssl_ciphers":
                http_ssl_ciphers = value

        for inner_directive, inner_args, inner_body in _split_nginx_blocks(body):
            if inner_directive.lower() != "server":
                continue

            listen = ""
            port = ""
            ssl_flag = False
            server_names: list[str] = []
            docroot = ""
            ssl_cert = ""
            ssl_key = ""
            ssl_protocols = ""
            ssl_ciphers = ""
            access_log = ""
            error_log = ""
            proxy_targets = []

            for name, value in _nginx_top_level_directives(inner_body):
                if name == "listen":
                    listen = value
                    ssl_flag = "ssl" in value.split()
                    port_token = value.split()[0] if value.split() else ""
                    port = port_token.rsplit(":", 1)[-1] if ":" in port_token else port_token
                elif name == "server_name":
                    server_names.extend(v for v in value.split() if v)
                elif name == "root":
                    docroot = value
                elif name == "ssl_certificate":
                    ssl_cert = value
                elif name == "ssl_certificate_key":
                    ssl_key = value
                elif name == "ssl_protocols":
                    ssl_protocols = value
                elif name == "ssl_ciphers":
                    ssl_ciphers = value
                elif name == "access_log":
                    access_log = value.split()[0] if value.split() else value
                elif name == "error_log":
                    error_log = value.split()[0] if value.split() else value

            for loc_directive, loc_args, loc_body in _split_nginx_blocks(inner_body):
                if loc_directive.lower() != "location":
                    continue
                for name, value in _nginx_top_level_directives(loc_body):
                    if name == "proxy_pass":
                        proxy_targets.append(f"{loc_args.strip()} -> {value}" if loc_args else value)

            hostname = server_names[0] if server_names else ""
            aliases = server_names[1:]

            vhosts.append(
                {
                    "hostname": hostname,
                    "hostalias": ", ".join(dict.fromkeys(aliases)),
                    "port": port,
                    "listen": listen,
                    "docroot": docroot,
                    "ssl_flag": ssl_flag,
                    "ssl_certificate_file": ssl_cert,
                    "ssl_certificate_key_file": ssl_key,
                    "ssl_protocols": ssl_protocols or (http_ssl_protocols if ssl_flag else ""),
                    "ssl_ciphers": ssl_ciphers or (http_ssl_ciphers if ssl_flag else ""),
                    "logging": access_log,
                    "errorlog": error_log,
                    "proxy_summary": ", ".join(proxy_targets),
                }
            )

    return {"vhosts": vhosts}


PARSERS = {"webtob": parse_webtob, "apache": parse_apache, "nginx": parse_nginx}
