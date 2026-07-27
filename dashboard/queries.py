from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import (
    CharField,
    Count,
    DateField,
    DecimalField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
)

from core.models import Asset
from facts.models import FactFieldDefinition, HostFactValue, PendingChange
from webconfig.models import WebConfigSource, WebConfigSourceRevision, WebServiceDomain, WebtobVhost

LEADING_FIXED_COLUMNS = [
    {"key": "hostname", "label": "Hostname", "lookup": "hostname"},
    {"key": "primary_ip", "label": "IP", "lookup": "primary_ip"},
    {"key": "os_family", "label": "OS", "lookup": "hostfact__os_family"},
]

TRAILING_FIXED_COLUMNS = [
    {"key": "last_changed_at", "label": "최근 변경일", "lookup": "last_changed_at"},
    {"key": "last_seen_at", "label": "최근 반영일", "lookup": "hostfact__last_seen_at"},
]

_FIXED_LOOKUPS = {
    c["key"]: c["lookup"] for c in LEADING_FIXED_COLUMNS + TRAILING_FIXED_COLUMNS
}

_VALUE_FIELD_BY_TYPE = {
    FactFieldDefinition.ValueType.NUMBER: ("value_number", DecimalField()),
    FactFieldDefinition.ValueType.DATE: ("value_date", DateField()),
    FactFieldDefinition.ValueType.TEXT: ("value_text", CharField()),
    FactFieldDefinition.ValueType.BOOL: ("value_text", CharField()),
    FactFieldDefinition.ValueType.CHOICE: ("value_text", CharField()),
}


def get_dynamic_field_definitions():
    return (
        FactFieldDefinition.objects.filter(is_visible=True)
        .exclude(source=FactFieldDefinition.Source.FIXED)
        .prefetch_related("choices")
        .order_by("sort_order", "id")
    )


def _request_param(request, *names, default=None):
    for name in names:
        value = request.GET.get(name)
        if value:
            return value
    return default


def build_sort_columns(request, keys, default):
    """자산 대시보드(get_dashboard_columns)와 같은 정렬 토글 규칙(같은 컬럼 다시 누르면
    오름/내림차순 반전)을 다른 목록 화면에서도 쓰기 위한 범용 버전. keys는 정렬 가능한 컬럼
    key 목록, default는 기본 정렬값("-created_at"처럼 방향 포함 가능). 반환값은
    {key: {"next_sort": ...}} 형태라 템플릿에서 columns.<key>.next_sort로 바로 쓴다."""
    sort = _request_param(request, "sort", "ordering", default=default)
    current_key = sort.lstrip("-")
    current_desc = sort.startswith("-")

    columns = {}
    for key in keys:
        is_active = key == current_key
        next_sort = f"-{key}" if is_active and not current_desc else key
        columns[key] = {"next_sort": next_sort}
    return columns


def _parse_number(value):
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_date(value):
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def get_asset_queryset(request):
    dynamic_fields = list(get_dynamic_field_definitions())

    queryset = Asset.objects.select_related("hostfact").prefetch_related(
        Prefetch(
            "hostfact__values",
            queryset=HostFactValue.objects.select_related("field_definition"),
        )
    )

    q = _request_param(request, "q", "search")
    if q:
        search_q = Q(hostname__icontains=q) | Q(primary_ip__icontains=q)
        for field_definition in dynamic_fields:
            if not field_definition.is_searchable:
                continue

            if field_definition.value_type == FactFieldDefinition.ValueType.NUMBER:
                parsed_number = _parse_number(q)
                if parsed_number is not None:
                    search_q |= Q(
                        hostfact__values__field_definition=field_definition,
                        hostfact__values__value_number=parsed_number,
                    )
            elif field_definition.value_type == FactFieldDefinition.ValueType.DATE:
                parsed_date = _parse_date(q)
                if parsed_date is not None:
                    search_q |= Q(
                        hostfact__values__field_definition=field_definition,
                        hostfact__values__value_date=parsed_date,
                    )
            else:
                search_q |= Q(
                    hostfact__values__field_definition=field_definition,
                    hostfact__values__value_text__icontains=q,
                )
        queryset = queryset.filter(search_q).distinct()

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")

    if sort_key in _FIXED_LOOKUPS:
        queryset = queryset.order_by(f"{direction}{_FIXED_LOOKUPS[sort_key]}")
    else:
        field_definition = next((f for f in dynamic_fields if f.key == sort_key), None)
        if field_definition:
            value_field, output_field = _VALUE_FIELD_BY_TYPE[field_definition.value_type]
            subquery = HostFactValue.objects.filter(
                host_fact=OuterRef("hostfact__pk"), field_definition=field_definition
            ).values(value_field)[:1]
            queryset = queryset.annotate(
                _dynamic_sort=Subquery(subquery, output_field=output_field)
            ).order_by(f"{direction}_dynamic_sort")
        else:
            queryset = queryset.order_by("hostname")

    return queryset


def get_dashboard_columns(request):
    sort = _request_param(request, "sort", "ordering", default="hostname")
    current_key = sort.lstrip("-")
    current_desc = sort.startswith("-")

    def _fixed_column(column):
        is_active = column["key"] == current_key
        next_sort = f"-{column['key']}" if is_active and not current_desc else column["key"]
        return {**column, "is_active": is_active, "next_sort": next_sort}

    columns = [_fixed_column(column) for column in LEADING_FIXED_COLUMNS]

    for field_definition in get_dynamic_field_definitions():
        is_active = field_definition.key == current_key
        next_sort = (
            f"-{field_definition.key}" if is_active and not current_desc else field_definition.key
        )
        columns.append(
            {
                "key": field_definition.key,
                "label": field_definition.label,
                "is_active": is_active,
                "next_sort": next_sort,
                "is_dynamic": True,
                "is_manual": field_definition.source == FactFieldDefinition.Source.MANUAL,
                "field_id": field_definition.id,
                "choices": (
                    [c.value for c in field_definition.choices.all()]
                    if field_definition.value_type == FactFieldDefinition.ValueType.CHOICE
                    else None
                ),
            }
        )

    columns.extend(_fixed_column(column) for column in TRAILING_FIXED_COLUMNS)

    return columns


CHANGE_HISTORY_SORT_LOOKUPS = {
    "created_at": "created_at",
    "decided_at": "decided_at",
    "status": "status",
    "asset": "asset__hostname",
}


def get_change_history_queryset(request):
    queryset = PendingChange.objects.select_related("asset", "field_definition")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q) | Q(field_definition__label__icontains=q)
        )

    change_status = request.GET.get("status")
    if change_status:
        queryset = queryset.filter(status=change_status)

    sort = _request_param(request, "sort", "ordering", default="-created_at")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = CHANGE_HISTORY_SORT_LOOKUPS.get(sort_key, "created_at")

    return queryset.order_by(f"{direction}{lookup}")


WEB_SERVICE_SORT_LOOKUPS = {
    "domain": "domain",
    "port": "port",
    "service_name": "service_name",
    "hostname": "source__asset__hostname",
    "kind": "source__kind",
}


def get_web_service_queryset(request):
    queryset = WebServiceDomain.objects.select_related("source__asset")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(domain__icontains=q)
            | Q(aliases__icontains=q)
            | Q(service_name__icontains=q)
            | Q(source__asset__hostname__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="domain")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = WEB_SERVICE_SORT_LOOKUPS.get(sort_key, "domain")

    return queryset.order_by(f"{direction}{lookup}")


WEBCONFIG_SORT_LOOKUPS = {
    "hostname": "asset__hostname",
    "kind": "kind",
    "solution_version": "solution_version",
    "solution_fix": "solution_fix",
    "vhost_count": "vhost_count",
    "last_changed_at": "last_changed_at",
    "last_pushed_at": "last_pushed_at",
}


def get_webconfig_queryset(request):
    queryset = WebConfigSource.objects.select_related("asset").annotate(
        vhost_count=Count("vhosts", distinct=True),
        last_changed_at=Max("revisions__detected_at"),
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q)
            | Q(vhosts__hostname__icontains=q)
            | Q(vhosts__hostalias__icontains=q)
        ).distinct()

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = WEBCONFIG_SORT_LOOKUPS.get(sort_key, "asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def get_webconfig_history_queryset(request):
    queryset = WebConfigSourceRevision.objects.select_related("source__asset")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(source__asset__hostname__icontains=q)

    return queryset.order_by("-detected_at")


WEBTOB_VHOST_SORT_LOOKUPS = {
    "hostname": "source__asset__hostname",
    "vhost_name": "name",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl__protocols",
    "ssl_ciphers": "ssl__required_ciphers",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service_name",
    "limit_request_body": "source__node__limit_request_body",
}


def get_webtob_vhost_queryset(request):
    queryset = WebtobVhost.objects.select_related("source__asset", "source__node", "ssl").prefetch_related(
        "svrgroups__servers", "uris__server"
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(name__icontains=q)
            | Q(hostname__icontains=q)
            | Q(hostalias__icontains=q)
            | Q(service_name__icontains=q)
        ).distinct()

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = WEBTOB_VHOST_SORT_LOOKUPS.get(sort_key, "source__asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def build_webtob_vhost_rows(vhosts):
    """vhost 목록 화면용 - SvrGroup/Server/URI는 vhost 하나에 여러 개씩 걸릴 수 있어(관계형
    구조) 표 한 칸에 요약 문자열로 모아준다(모달 없이 표 안에서 다 보여주기 위함)."""
    rows = []
    for vhost in vhosts:
        svrgroup_parts = []
        server_parts = []
        for svrgroup in vhost.svrgroups.all():
            svrgroup_parts.append(
                f"{svrgroup.name}({svrgroup.svrtype})" if svrgroup.svrtype else svrgroup.name
            )
            for server in svrgroup.servers.all():
                if server.minproc is not None or server.maxproc is not None:
                    proc_range = f"({server.minproc if server.minproc is not None else ''}~{server.maxproc if server.maxproc is not None else ''})"
                else:
                    proc_range = ""
                server_parts.append(f"{server.name}{proc_range}")

        uri_parts = [uri.uri_path or uri.name for uri in vhost.uris.all()]

        rows.append(
            {
                "vhost": vhost,
                "svrgroup_summary": ", ".join(svrgroup_parts),
                "server_summary": ", ".join(server_parts),
                "uri_summary": ", ".join(uri_parts),
            }
        )
    return rows


def build_rows(assets, dynamic_field_definitions):
    rows = []
    for asset in assets:
        hostfact = getattr(asset, "hostfact", None)
        values_by_field_id = {}
        if hostfact is not None:
            for value in hostfact.values.all():
                # value_text가 None 대신 빈 문자열("")로 저장된 경우도 "값 없음"으로 취급해
                # value_number/value_date로 폴백하도록 한다.
                candidates = (value.value_text, value.value_number, value.value_date)
                values_by_field_id[value.field_definition_id] = next(
                    (v for v in candidates if v not in (None, "")), None
                )

        dynamic_cells = [
            {
                "value": values_by_field_id.get(fd.id),
                "field_id": fd.id,
                "label": fd.label,
                "is_manual": fd.source == FactFieldDefinition.Source.MANUAL,
                "value_type": fd.value_type,
            }
            for fd in dynamic_field_definitions
        ]
        rows.append({"asset": asset, "hostfact": hostfact, "dynamic_cells": dynamic_cells})

    return rows
