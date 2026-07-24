from django.db import transaction

from webconfig.models import (
    WebConfigSource,
    WebtobNode,
    WebtobServer,
    WebtobSsl,
    WebtobSvrGroup,
    WebtobUri,
    WebtobVhost,
)

STRUCTURED_SECTIONS = {"NODE", "SSL", "VHOST", "SVRGROUP", "SERVER", "URI"}


def _is_yes(value: str | None) -> bool:
    return (value or "").strip().lower() in ("y", "yes", "true", "1")


def _to_int(value: str | None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_vhosts(vhost_names_attr: str | None, vhost_by_name: dict) -> list:
    if not vhost_names_attr:
        return []
    names = [n.strip() for n in vhost_names_attr.split(",") if n.strip()]
    return [vhost_by_name[n] for n in names if n in vhost_by_name]


@transaction.atomic
def sync_webtob(source: WebConfigSource, sections: dict) -> None:
    """파싱된 섹션 dict로 이 source에 딸린 구조화 테이블을 재생성한다.
    VHost만 이름으로 upsert(수기 입력한 service_name 보존), 나머지는 통짜 재생성."""
    WebtobUri.objects.filter(source=source).delete()
    WebtobServer.objects.filter(source=source).delete()
    WebtobSvrGroup.objects.filter(source=source).delete()
    WebtobSsl.objects.filter(source=source).delete()
    WebtobNode.objects.filter(source=source).delete()

    node_section = sections.get("NODE") or {}
    if node_section:
        node_name, node_attrs = next(iter(node_section.items()))
        WebtobNode.objects.create(
            source=source,
            name=node_name,
            webtobdir=node_attrs.get("webtobdir", ""),
            docroot=node_attrs.get("docroot", ""),
            port=node_attrs.get("port", ""),
            hth=node_attrs.get("hth", ""),
        )

    ssl_by_name = {}
    for name, attrs in (sections.get("SSL") or {}).items():
        ssl_by_name[name] = WebtobSsl.objects.create(
            source=source,
            name=name,
            certificate_file=attrs.get("certificatefile", ""),
            certificate_key_file=attrs.get("certificatekeyfile", ""),
            protocols=attrs.get("protocols", ""),
            required_ciphers=attrs.get("requiredciphers", ""),
        )

    vhost_by_name = {}
    vhost_section = sections.get("VHOST") or {}
    for name, attrs in vhost_section.items():
        vhost, _ = WebtobVhost.objects.update_or_create(
            source=source,
            name=name,
            defaults=dict(
                hostname=attrs.get("hostname", ""),
                hostalias=attrs.get("hostalias", ""),
                docroot=attrs.get("docroot", ""),
                port=attrs.get("port", ""),
                ssl_flag=_is_yes(attrs.get("sslflag")),
                ssl=ssl_by_name.get(attrs.get("sslname")),
                logging=attrs.get("logging", ""),
                errorlog=attrs.get("errorlog", ""),
            ),
        )
        vhost_by_name[name] = vhost

    # 이번 push에서 더 이상 안 보이는 vhost만 정리(수기 입력 보존을 위해 통짜 삭제 대신 이 방식 사용)
    WebtobVhost.objects.filter(source=source).exclude(name__in=vhost_section.keys()).delete()

    svrgroup_by_name = {}
    for name, attrs in (sections.get("SVRGROUP") or {}).items():
        svrgroup = WebtobSvrGroup.objects.create(
            source=source, name=name, svrtype=attrs.get("svrtype", "")
        )
        svrgroup.vhosts.set(_resolve_vhosts(attrs.get("vhostname"), vhost_by_name))
        svrgroup_by_name[name] = svrgroup

    server_by_name = {}
    for name, attrs in (sections.get("SERVER") or {}).items():
        server_by_name[name] = WebtobServer.objects.create(
            source=source,
            name=name,
            svrgroup=svrgroup_by_name.get(attrs.get("svgname")),
            minproc=_to_int(attrs.get("minproc")),
            maxproc=_to_int(attrs.get("maxproc")),
        )

    for name, attrs in (sections.get("URI") or {}).items():
        uri = WebtobUri.objects.create(
            source=source,
            name=name,
            uri_path=attrs.get("uri", ""),
            server=server_by_name.get(attrs.get("svrname")),
        )
        uri.vhosts.set(_resolve_vhosts(attrs.get("vhostname"), vhost_by_name))

    source.extra_sections = {k: v for k, v in sections.items() if k not in STRUCTURED_SECTIONS}
    source.save(update_fields=["extra_sections"])
