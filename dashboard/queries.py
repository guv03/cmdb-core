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
from facts.models import FactFieldDefinition, HostFact, HostFactValue, PendingChange
from processes.models import ProcessSnapshot
from was.models import JeusContainer, WasConfigSource, WasConfigSourceRevision
from webconfig.models import (
    ApacheVhost,
    NginxVhost,
    WebConfigSource,
    WebConfigSourceRevision,
    WebServiceDomain,
    WebtobVhost,
)

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


def _kind_search_q(choices_class, field_name, q):
    """kind 필드 검색 조건. 원시값(webtob/jeus8 등)뿐 아니라 표시 라벨("JEUS 8"처럼 원시값과
    다르게 공백/대소문자가 섞인 경우가 있어)로 검색해도 매칭되게 라벨이 q를 포함하는 원시값들도
    같이 묶는다."""
    matching_keys = [key for key, label in choices_class.choices if q.lower() in label.lower()]
    q_obj = Q(**{f"{field_name}__icontains": q})
    if matching_keys:
        q_obj |= Q(**{f"{field_name}__in": matching_keys})
    return q_obj


# 통합대시보드 각 섹션(OS/WEB/WAS)에서 카테고리별로 각자 색을 받는 최대 개수 - dataviz
# 원칙상 카테고리 색은 고정 개수만 배정하고 그 이상은 "기타"로 접는다(9번째 색을 새로
# 만들지 않음). 세 섹션이 전부 같은 색 순서를 공유해도 서로 다른 카테고리 축(OS Family vs
# WEB/WAS 종류)이라 섹션 간에 헷갈릴 일은 없다.
CATEGORY_COLOR_SLOTS = ["s1", "s2", "s3", "s4", "s5"]


def _build_category_tiles(rows, total, missing_label="(미수집)"):
    """OS/WEB/WAS 통합대시보드 섹션 공통 타일 빌더. rows는 이미 count 내림차순으로 정렬된
    [{"key": 드릴다운에 쓸 원본 값, "name": 화면에 보일 라벨, "count": 개수}, ...]. 상위
    5개만 각자 색을 받고 나머지는 "기타"로 접으며, count 합계가 total에 못 미치면 그 차이를
    missing_label 타일로 채운다(WEB/WAS의 kind처럼 항상 다 채워지는 필드는 차이가 0이라
    이 타일이 아예 안 생긴다 - OS의 "(미수집)"에서만 실제로 나타남)."""
    tiles = []
    for i, row in enumerate(rows[: len(CATEGORY_COLOR_SLOTS)]):
        tiles.append(
            {
                "key": row["key"],
                "name": row["name"],
                "count": row["count"],
                "slot": CATEGORY_COLOR_SLOTS[i],
                "clickable": True,
            }
        )

    other_count = sum(row["count"] for row in rows[len(CATEGORY_COLOR_SLOTS) :])
    if other_count:
        tiles.append({"name": "기타", "count": other_count, "slot": "s6", "clickable": False})

    missing = total - sum(row["count"] for row in rows)
    if missing:
        tiles.append({"name": missing_label, "count": missing, "slot": None, "clickable": False})

    return tiles


def _breakdown_by_field(queryset, field_name):
    """통합대시보드 드릴다운 공통 - queryset을 field_name 기준으로 묶어 개수를 센다.
    field_name이 비어있는 행(아직 그 값까지는 안 잡힌 경우)은 "(버전 미상)"으로 묶는다."""
    rows = [
        {"name": row[field_name], "count": row["count"]}
        for row in queryset.exclude(**{field_name: ""})
        .values(field_name)
        .annotate(count=Count("id"))
        .order_by("-count", field_name)
    ]
    unknown = queryset.count() - sum(row["count"] for row in rows)
    if unknown:
        rows.append({"name": "(버전 미상)", "count": unknown})
    return rows


def get_os_overview_data():
    """통합대시보드 OS 섹션 - OS Family별 자산 수. os_family는 CharField라(TextField 아님)
    GROUP BY해도 Oracle NCLOB 문제 없음."""
    total = Asset.objects.count()
    rows = [
        {"key": row["os_family"], "name": row["os_family"], "count": row["count"]}
        for row in HostFact.objects.exclude(os_family="")
        .values("os_family")
        .annotate(count=Count("id"))
        .order_by("-count", "os_family")
    ]
    return {"total": total, "tiles": _build_category_tiles(rows, total)}


def get_os_version_breakdown(os_family):
    """통합대시보드 OS 섹션의 Family 타일 클릭 시 드릴다운 - 그 Family 안에서 os_version별 개수."""
    return _breakdown_by_field(HostFact.objects.filter(os_family=os_family), "os_version")


WEB_KIND_LABELS = dict(WebConfigSource.Kind.choices)


def get_web_overview_data():
    """통합대시보드 WEB 섹션 - 종류(webtob/apache/nginx)별 소스(서버) 수. OS의 os_family
    자리에 kind가 들어가는 것 말고는 동일한 구조 - kind는 항상 값이 있어(CharField, blank
    아님) "(미수집)" 타일은 실제로는 절대 안 나타난다."""
    total = WebConfigSource.objects.count()
    rows = [
        {"key": row["kind"], "name": WEB_KIND_LABELS.get(row["kind"], row["kind"]), "count": row["count"]}
        for row in WebConfigSource.objects.values("kind").annotate(count=Count("id")).order_by("-count", "kind")
    ]
    return {"total": total, "tiles": _build_category_tiles(rows, total)}


def get_web_version_breakdown(kind):
    """통합대시보드 WEB 섹션의 종류 타일 클릭 시 드릴다운 - 그 종류 안에서 솔루션 버전별 개수."""
    return _breakdown_by_field(WebConfigSource.objects.filter(kind=kind), "solution_version")


WAS_KIND_LABELS = dict(WasConfigSource.Kind.choices)


def get_was_overview_data():
    """통합대시보드 WAS 섹션 - get_web_overview_data와 동일 구조(지금은 kind가 jeus8
    하나뿐이라 타일도 하나뿐이지만, 확장성을 위해 WEB과 똑같이 kind 축을 그대로 둔다 -
    JEUS6 등 새 kind가 추가되면 코드 변경 없이 타일이 자동으로 늘어남)."""
    total = WasConfigSource.objects.count()
    rows = [
        {"key": row["kind"], "name": WAS_KIND_LABELS.get(row["kind"], row["kind"]), "count": row["count"]}
        for row in WasConfigSource.objects.values("kind").annotate(count=Count("id")).order_by("-count", "kind")
    ]
    return {"total": total, "tiles": _build_category_tiles(rows, total)}


def get_was_version_breakdown(kind):
    """통합대시보드 WAS 섹션의 종류 타일 클릭 시 드릴다운 - 그 종류 안에서 솔루션 버전별 개수."""
    return _breakdown_by_field(WasConfigSource.objects.filter(kind=kind), "solution_version")


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
        search_q = (
            Q(hostname__icontains=q)
            | Q(primary_ip__icontains=q)
            | Q(hostfact__os_family__icontains=q)
        )
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
    # annotate()의 집계 함수는 .values() 없이 쓰면 선택된 전체 필드로 암묵적 GROUP BY를
    # 만드는데, raw_content/extra_sections는 Oracle에서 NCLOB으로 매핑돼 GROUP BY 대상이
    # 되면 ORA-00932가 난다(Postgres는 문제없어 로컬에서는 안 잡힘). 목록 화면은 두 필드를
    # 안 쓰므로 annotate 전에 defer로 빼둔다.
    # vhost_count: 소스 하나는 항상 단일 kind라 vhosts/apache_vhosts/nginx_vhosts 중
    # 최대 하나만 0이 아니다 - kind 무관하게 세 Count(distinct)를 더해서 정확한 값을 얻는다.
    queryset = (
        WebConfigSource.objects.select_related("asset")
        .defer("raw_content", "extra_sections")
        .annotate(
            vhost_count=(
                Count("vhosts", distinct=True)
                + Count("apache_vhosts", distinct=True)
                + Count("nginx_vhosts", distinct=True)
            ),
            last_changed_at=Max("revisions__detected_at"),
        )
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q)
            | Q(vhosts__hostname__icontains=q)
            | Q(vhosts__hostalias__icontains=q)
            | Q(apache_vhosts__hostname__icontains=q)
            | Q(apache_vhosts__hostalias__icontains=q)
            | Q(nginx_vhosts__hostname__icontains=q)
            | Q(nginx_vhosts__hostalias__icontains=q)
            | _kind_search_q(WebConfigSource.Kind, "kind", q)
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


# ssl_ciphers는 일부러 뺐다 - WebtobSsl.required_ciphers가 TextField(Oracle NCLOB)라
# 정렬 대상이 되면 ORA-00932 위험이 있음(apache/nginx의 ssl_ciphers와 같은 이유,
# APACHE_VHOST_SORT_LOOKUPS 주석 참고). ssl_protocols는 CharField라 안전.
WEBTOB_VHOST_SORT_LOOKUPS = {
    "hostname": "source__asset__hostname",
    "vhost_name": "name",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl__protocols",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service_name",
    "limit_request_body": "source__node__limit_request_body",
}


def get_webtob_vhost_queryset(request):
    # select_related("source__...", "ssl")가 raw_content/extra_sections(WebConfigSource)와
    # required_ciphers(WebtobSsl) 같은 TextField(Oracle에서 NCLOB)를 같이 끌고 오는데,
    # 예전엔 검색 시 .distinct()를 걸어서 이 컬럼들까지 DISTINCT 대상에 들어가 ORA-00932가
    # 났었다(get_webconfig_queryset의 GROUP BY 문제와 동일 원인, 1.0.12 참고). 지금 이
    # 쿼리의 검색 필터는 own 필드/forward FK만 참조해 to-many 조인이 없으므로(중복 행이
    # 생길 수 없음) .distinct() 자체가 불필요 - defer로 필드를 더 늘리는 대신 아예 제거해서
    # 근본적으로 피한다.
    queryset = (
        WebtobVhost.objects.select_related("source__asset", "source__node", "ssl")
        .defer("source__raw_content", "source__extra_sections")
        .prefetch_related("svrgroups__servers", "uris__server")
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(name__icontains=q)
            | Q(hostname__icontains=q)
            | Q(hostalias__icontains=q)
            | Q(service_name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = WEBTOB_VHOST_SORT_LOOKUPS.get(sort_key, "source__asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


# ssl_ciphers는 일부러 뺐다 - TextField(Oracle NCLOB)라 정렬 대상이 되면 WebtobVhost의
# required_ciphers와 같은 이유로 ORA-00932 위험이 있음(CLAUDE.md의 NCLOB 규칙, ORDER BY도
# 대상). ssl_protocols는 CharField라 안전.
APACHE_VHOST_SORT_LOOKUPS = {
    "hostname": "source__asset__hostname",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl_protocols",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service_name",
}

NGINX_VHOST_SORT_LOOKUPS = {
    "hostname": "source__asset__hostname",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl_protocols",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service_name",
}


def get_apache_vhost_queryset(request):
    # WebToB의 get_webtob_vhost_queryset과 같은 패턴(NCLOB 대응, kind 전용 목록 화면).
    # SvrGroup/Server/Uri 같은 관계형 테이블이 없어 prefetch_related는 불필요.
    # proxy_summary(TextField, Oracle NCLOB)는 목록에 그대로 노출해야 해서 defer로 뺄 수
    # 없는데, 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없으므로(중복 행이
    # 생길 수 없음) .distinct()가 애초에 불필요 - 걸지 않아서 NCLOB DISTINCT 문제를 피한다.
    queryset = ApacheVhost.objects.select_related("source__asset").defer(
        "source__raw_content", "source__extra_sections"
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(hostname__icontains=q)
            | Q(hostalias__icontains=q)
            | Q(service_name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = APACHE_VHOST_SORT_LOOKUPS.get(sort_key, "source__asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def get_nginx_vhost_queryset(request):
    # get_apache_vhost_queryset과 동일한 이유로 .distinct() 없음(proxy_summary NCLOB 대응).
    queryset = NginxVhost.objects.select_related("source__asset").defer(
        "source__raw_content", "source__extra_sections"
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(hostname__icontains=q)
            | Q(hostalias__icontains=q)
            | Q(service_name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = NGINX_VHOST_SORT_LOOKUPS.get(sort_key, "source__asset__hostname")

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


WAS_CONFIG_SORT_LOOKUPS = {
    "hostname": "asset__hostname",
    "kind": "kind",
    "solution_version": "solution_version",
    "container_count": "container_count",
    "last_changed_at": "last_changed_at",
    "last_pushed_at": "last_pushed_at",
}


def get_was_config_queryset(request):
    # get_webconfig_queryset과 같은 이유로 raw_content(TextField, Oracle NCLOB)를 defer.
    queryset = (
        WasConfigSource.objects.select_related("asset")
        .defer("raw_content")
        .annotate(
            container_count=Count("containers", distinct=True),
            last_changed_at=Max("revisions__detected_at"),
        )
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q)
            | Q(containers__node_name__icontains=q)
            | Q(containers__name__icontains=q)
            | _kind_search_q(WasConfigSource.Kind, "kind", q)
        ).distinct()

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = WAS_CONFIG_SORT_LOOKUPS.get(sort_key, "asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def get_was_history_queryset(request):
    queryset = WasConfigSourceRevision.objects.select_related("source__asset")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(source__asset__hostname__icontains=q)

    return queryset.order_by("-detected_at")


JEUS_CONTAINER_SORT_LOOKUPS = {
    "hostname": "asset__hostname",
    "node_name": "node_name",
    "container": "name",
    "listen_port": "listen_port",
    "ssl_port": "ssl_port",
    "service_name": "service_name",
}


def get_jeus_container_queryset(request):
    # 목록에 deployed_apps_summary(TextField, Oracle NCLOB)를 그대로 노출해야 해서 defer로
    # 뺄 수 없는데, 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없으므로(중복
    # 행이 생길 수 없음) .distinct()가 애초에 불필요 - 걸지 않아서 NCLOB 문제를 피한다
    # (apache/nginx vhost 목록에서 확립한 원칙과 동일).
    queryset = (
        JeusContainer.objects.select_related("source__asset", "asset")
        .defer("source__raw_content")
        .prefetch_related("webtob_connectors__webtob_server__source__asset")
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(asset__hostname__icontains=q)
            | Q(node_name__icontains=q)
            | Q(name__icontains=q)
            | Q(service_name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = JEUS_CONTAINER_SORT_LOOKUPS.get(sort_key, "asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def build_jeus_container_rows(containers):
    """webtob-connector는 컨테이너 하나에 여러 개씩 걸릴 수 있어(관계형 구조) 표 한 칸에
    요약 문자열로 모아준다 - build_webtob_vhost_rows와 같은 패턴."""
    rows = []
    for container in containers:
        connector_parts = []
        for connector in container.webtob_connectors.all():
            target = f"{connector.network_address}:{connector.port}" if connector.port else connector.network_address
            if connector.webtob_server is not None:
                label = f"{connector.registration_id}@{connector.webtob_server.source.asset.hostname}"
            else:
                label = f"{connector.registration_id}(WebToB 쪽 미확인)"
            connector_parts.append(f"{label} -> {target}")

        rows.append({"container": container, "webtob_connector_summary": ", ".join(connector_parts)})
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


PROCESS_SORT_LOOKUPS = {
    "hostname": "asset__hostname",
    "collected_at": "collected_at",
}


def get_process_queryset(request):
    # raw_output은 TextField(Oracle에서 NCLOB)라 목록 화면에서는 절대 select하지 않는다 -
    # 검색 시 아래 .distinct()가 NCLOB 컬럼까지 끌고 들어가면 오늘 이 세션에 두 번 겪은
    # ORA-00932(GROUP BY/DISTINCT NCLOB)가 재현된다. 원본은 상세 화면에서만 별도 쿼리로 가져온다.
    queryset = (
        ProcessSnapshot.objects.select_related("asset")
        .defer("raw_output")
        .prefetch_related("detected_applications__definition")
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q) | Q(detected_applications__definition__name__icontains=q)
        ).distinct()

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = PROCESS_SORT_LOOKUPS.get(sort_key, "asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")
