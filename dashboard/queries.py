from collections import defaultdict
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

from core.models import Asset, Service
from database.models import (
    DbConfigSource,
    DbConfigSourceFieldDefinition,
    DbConfigSourceRevision,
    DbInstance,
)
from facts.models import FactChangeHistory, FactFieldDefinition, HostFact, HostFactValue
from network.models import NetworkRoute, NetworkRouteBackend
from processes.models import ProcessSnapshot
from systems.models import SystemHost, SystemHostFieldDefinition, SystemSource, SystemVm
from was.models import JeusContainer, JeusDataSource, WasConfigSource, WasConfigSourceRevision
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
        .prefetch_related("choices")
        .order_by("sort_order", "id")
    )


def _request_param(request, *names, default=None):
    for name in names:
        value = request.GET.get(name)
        if value:
            return value
    return default


def describe_overview_filter(request, *fields):
    """통합대시보드 도넛의 버전 조각 클릭으로 이 목록 화면(assets/webconfig/was)에 정확
    일치 필터(os_family/os_version, kind/solution_version)가 걸려 들어온 경우, 화면 상단에
    "지금 이 조건으로 좁혀져 있다"를 보여주기 위한 라벨을 만든다. fields는
    (query_param, 표시라벨[, 코드값→사람이 읽는 라벨 변환함수]) 튜플 목록 - kind처럼 원본
    값이 코드값(webtob 등)인 경우에만 세 번째 인자를 넘긴다."""
    parts = []
    for param, label, *transform in fields:
        value = request.GET.get(param)
        if value:
            display = transform[0](value) if transform else value
            parts.append(f"{label}: {display}")
    return " · ".join(parts)


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
    """kind 필드 검색 조건. 원시값(webtob/jeus 등)뿐 아니라 표시 라벨("WebToB"처럼 원시값과
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


UNKNOWN_VERSION_LABEL = "(버전 미상)"


def _breakdown_by_field(queryset, field_name):
    """통합대시보드 드릴다운 공통 - queryset을 field_name 기준으로 묶어 개수를 센다.
    field_name이 비어있는 행(아직 그 값까지는 안 잡힌 경우)은 UNKNOWN_VERSION_LABEL로 묶는다."""
    rows = [
        {"name": row[field_name], "count": row["count"]}
        for row in queryset.exclude(**{field_name: ""})
        .values(field_name)
        .annotate(count=Count("id"))
        .order_by("-count", field_name)
    ]
    unknown = queryset.count() - sum(row["count"] for row in rows)
    if unknown:
        rows.append({"name": UNKNOWN_VERSION_LABEL, "count": unknown})
    return rows


def _filter_by_version(queryset, field_name, version):
    """도넛 드릴다운 목록 모달 공통 - version이 UNKNOWN_VERSION_LABEL이면 그 필드가
    비어있는 행을, 아니면 정확히 일치하는 행을 걸러낸다(_breakdown_by_field의 집계와
    같은 기준을 목록 조회에도 그대로 적용)."""
    if version == UNKNOWN_VERSION_LABEL:
        return queryset.filter(**{field_name: ""})
    return queryset.filter(**{field_name: version})


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
    """통합대시보드 WAS 섹션 - get_web_overview_data와 동일 구조(지금은 kind가 jeus
    하나뿐이라 타일도 하나뿐이지만, 확장성을 위해 WEB과 똑같이 kind 축을 그대로 둔다 -
    jeus6 등 새 kind가 추가되면 코드 변경 없이 타일이 자동으로 늘어남)."""
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

    # hostfact.raw_facts(JSONField, Oracle NCLOB)를 select_related가 SELECT 목록에 끌고
    # 들어오는데, 검색 시 아래 .distinct()가 걸리면(동적 필드 검색은 hostfact__values로
    # to-many 조인까지 생김) ORA-00932(GROUP BY/DISTINCT에 NCLOB)가 난다 - webconfig 등
    # 다른 쿼리셋에 이미 적용된 defer 패턴과 동일하게 방어(CLAUDE.md NCLOB 규칙).
    queryset = Asset.objects.select_related("hostfact").defer("hostfact__raw_facts").prefetch_related(
        Prefetch(
            "hostfact__values",
            queryset=HostFactValue.objects.select_related("field_definition"),
        )
    )

    # 통합대시보드 OS 도넛의 버전 조각 클릭 시 "이 화면을 그대로" 필터해서 모달로 보여주기
    # 위한 정확 일치 필터 - q(부분일치 통합검색)와 별개 축이라 함께 걸려도 AND로 좁혀진다.
    # hostfact는 O2O라 이 필터 자체는 to-many 조인을 만들지 않으므로 .distinct() 필요 없음.
    os_family = _request_param(request, "os_family")
    if os_family:
        queryset = queryset.filter(hostfact__os_family=os_family)
    os_version = _request_param(request, "os_version")
    if os_version:
        queryset = _filter_by_version(queryset, "hostfact__os_version", os_version)

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


# webconfig/was의 *Revision 이력 조회와 동일한 취지 - 승인/반려 없는 읽기 전용 이력이라
# status 관련 필터/정렬은 없다.
CHANGE_HISTORY_SORT_LOOKUPS = {
    "detected_at": "detected_at",
    "asset": "asset__hostname",
}


def get_change_history_queryset(request):
    queryset = FactChangeHistory.objects.select_related("asset")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q) | Q(field_label__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="-detected_at")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = CHANGE_HISTORY_SORT_LOOKUPS.get(sort_key, "detected_at")

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


def get_service_container_queryset(request):
    """서비스 탭의 WAS(컨테이너) 표 - WEB(WebServiceDomain) 표와 같은 검색창(q)을 공유한다.
    WAS 설치 규모는 WEB vhost 대비 훨씬 작은 게 보통이라(이 프로젝트 실측 기준) 별도
    정렬/페이지네이션 없이 이름순으로 전부 보여준다 - 필요해지면 그때 추가."""
    queryset = JeusContainer.objects.select_related("asset", "source", "service")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q)
            | Q(node_name__icontains=q)
            | Q(name__icontains=q)
            | Q(service__name__icontains=q)
        )

    return queryset.order_by("name")


def get_service_manage_queryset(request):
    """"서비스 관리" 화면(Service 객체 자체의 생성/이름변경/삭제 - WEB/WAS 배정은 별개 화면인
    "서비스 배정"에서 다룬다) - 삭제 전에 얼마나 많은 곳에 배정돼있는지 참고할 수 있게
    배정 건수를 같이 보여준다. Service 자신은 TextField/JSONField가 없어 이 annotate는
    NCLOB GROUP BY 위험이 없다(CLAUDE.md 환경 섹션 참고)."""
    queryset = Service.objects.annotate(
        assignment_count=(
            Count("webtob_vhosts", distinct=True)
            + Count("apache_vhosts", distinct=True)
            + Count("nginx_vhosts", distinct=True)
            + Count("jeus_containers", distinct=True)
        )
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(name__icontains=q)

    return queryset.order_by("name")


def get_network_route_queryset(request):
    """네트워크 탭(최상위 메뉴) - 도메인/VIP 하나 = 행 하나인 독립 라우팅 테이블
    (NetworkRoute). 과거엔 Service 하위에 그룹핑된 화면이었으나, 서비스를 먼저 골라야 하는
    흐름이 실제 의도(도메인/VIP로 부르는 걸 보고 자동으로 추적)와 안 맞는다는 피드백으로
    서비스와 무관한 평범한 목록 화면으로 갈아엎었다(network.models.NetworkRoute 참고).
    NetworkRoute 필드는 전부 CharField(TextField/JSONField 아님)라 검색 필터에 .distinct()가
    필요해져도 Oracle NCLOB DISTINCT 제약(CLAUDE.md 환경 섹션)에 안 걸린다."""
    queryset = NetworkRoute.objects.prefetch_related(
        Prefetch("backends", queryset=NetworkRouteBackend.objects.select_related("asset"))
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(key__icontains=q)
            | Q(label__icontains=q)
            | Q(note__icontains=q)
            | Q(backends__ip_or_hostname__icontains=q)
        ).distinct()

    return queryset.order_by("key")


WEBCONFIG_SORT_LOOKUPS = {
    "hostname": "asset__hostname",
    "ip": "asset__primary_ip",
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

    # 통합대시보드 WEB 도넛의 버전 조각 클릭 시 이 화면을 그대로 필터해서 모달로 보여주기
    # 위한 정확 일치 필터 - kind/solution_version 모두 소스 자신의 필드라 조인이 안 생겨
    # 아래 q 필터의 .distinct()와 무관하게 안전하다.
    kind = _request_param(request, "kind")
    if kind:
        queryset = queryset.filter(kind=kind)
    solution_version = _request_param(request, "solution_version")
    if solution_version:
        queryset = _filter_by_version(queryset, "solution_version", solution_version)

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
    "ip": "source__asset__primary_ip",
    "vhost_name": "name",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl__protocols",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service__name",
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
        WebtobVhost.objects.select_related("source__asset", "source__node", "ssl", "service")
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
            | Q(service__name__icontains=q)
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
    "ip": "source__asset__primary_ip",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl_protocols",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service__name",
}

NGINX_VHOST_SORT_LOOKUPS = {
    "hostname": "source__asset__hostname",
    "ip": "source__asset__primary_ip",
    "domain": "hostname",
    "hostalias": "hostalias",
    "port": "port",
    "docroot": "docroot",
    "ssl_flag": "ssl_flag",
    "ssl_protocols": "ssl_protocols",
    "logging": "logging",
    "errorlog": "errorlog",
    "service_name": "service__name",
}


def get_apache_vhost_queryset(request):
    # WebToB의 get_webtob_vhost_queryset과 같은 패턴(NCLOB 대응, kind 전용 목록 화면).
    # SvrGroup/Server/Uri 같은 관계형 테이블이 없어 prefetch_related는 불필요.
    # proxy_summary(TextField, Oracle NCLOB)는 목록에 그대로 노출해야 해서 defer로 뺄 수
    # 없는데, 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없으므로(중복 행이
    # 생길 수 없음) .distinct()가 애초에 불필요 - 걸지 않아서 NCLOB DISTINCT 문제를 피한다.
    queryset = ApacheVhost.objects.select_related("source__asset", "service").defer(
        "source__raw_content", "source__extra_sections"
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(hostname__icontains=q)
            | Q(hostalias__icontains=q)
            | Q(service__name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = APACHE_VHOST_SORT_LOOKUPS.get(sort_key, "source__asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def get_nginx_vhost_queryset(request):
    # get_apache_vhost_queryset과 동일한 이유로 .distinct() 없음(proxy_summary NCLOB 대응).
    queryset = NginxVhost.objects.select_related("source__asset", "service").defer(
        "source__raw_content", "source__extra_sections"
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(hostname__icontains=q)
            | Q(hostalias__icontains=q)
            | Q(service__name__icontains=q)
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
    "ip": "asset__primary_ip",
    "kind": "kind",
    "instance_name": "instance_name",
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

    # get_webconfig_queryset과 같은 이유(통합대시보드 WAS 도넛 버전 조각 클릭)의 정확 일치
    # 필터 - kind/solution_version 둘 다 소스 자신의 필드라 조인이 안 생겨 안전하다.
    kind = _request_param(request, "kind")
    if kind:
        queryset = queryset.filter(kind=kind)
    solution_version = _request_param(request, "solution_version")
    if solution_version:
        queryset = _filter_by_version(queryset, "solution_version", solution_version)

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q)
            | Q(instance_name__icontains=q)
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
    "ip": "asset__primary_ip",
    "instance_name": "source__instance_name",
    "node_name": "node_name",
    "container": "name",
    "listen_port": "listen_port",
    "ssl_port": "ssl_port",
    "service_name": "service__name",
}


def get_jeus_container_queryset(request):
    # 목록에 deployed_apps_summary(TextField, Oracle NCLOB)를 그대로 노출해야 해서 defer로
    # 뺄 수 없는데, 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없으므로(중복
    # 행이 생길 수 없음) .distinct()가 애초에 불필요 - 걸지 않아서 NCLOB 문제를 피한다
    # (apache/nginx vhost 목록에서 확립한 원칙과 동일).
    # kind=jeus/jeus6만 대상 - Tomcat은 설정에 들어가는 값 자체가 달라(WebToB 연결 개념이
    # 없음, node_name이 hostname과 동일해 의미가 없음 등) get_tomcat_container_queryset로
    # 완전히 분리했다(webconfig의 WebToB/Apache/Nginx vhost 목록을 kind별로 나눈 것과 동일
    # 원칙 - JeusContainer 모델은 공유해도 화면은 공유하지 않음).
    queryset = (
        JeusContainer.objects.filter(
            source__kind__in=[WasConfigSource.Kind.JEUS, WasConfigSource.Kind.JEUS6]
        )
        .select_related("source__asset", "asset", "service")
        .defer("source__raw_content")
        .prefetch_related(
            "webtob_connectors__webtob_server__source__asset",
            "manual_routes",
            "manual_db_sources",
        )
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(source__instance_name__icontains=q)
            | Q(asset__hostname__icontains=q)
            | Q(node_name__icontains=q)
            | Q(name__icontains=q)
            | Q(service__name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = JEUS_CONTAINER_SORT_LOOKUPS.get(sort_key, "asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def format_manual_route_label(route):
    """JeusContainer.manual_routes 표시용 - network 탭의 label(구분용 이름)이 있으면 key와
    같이, 없으면 key만. JeusContainerManualRouteUpdateView(dashboard/views.py)와 목록 행
    렌더링(build_jeus_container_rows/build_tomcat_container_rows) 양쪽에서 같이 쓴다."""
    return f"{route.label} ({route.key})" if route.label else route.key


def format_manual_db_source_label(source):
    """JeusContainer.manual_db_sources 표시용 - format_manual_route_label과 동일 취지."""
    return f"{source.db_unique_name} ({source.db_name})" if source.db_name else source.db_unique_name


def _manual_link_entries(container):
    """WAS 컨테이너 목록의 "호출 라우트"/"DB 연결" 두 컬럼이 공유하는 형태 - 수기 연결
    M2M을 모달/셀에 그대로 뿌리기 좋은 {id, label} 목록으로 바꾼다. prefetch_related로 이미
    받아온 캐시를 쓰도록 .all()에 파이썬 sorted()만 적용(.order_by()는 캐시를 우회해 컨테이너
    수만큼 추가 쿼리가 나가므로 피함)."""
    routes = sorted(container.manual_routes.all(), key=lambda r: r.key)
    db_sources = sorted(container.manual_db_sources.all(), key=lambda s: s.db_unique_name)
    return (
        [{"id": r.id, "label": format_manual_route_label(r)} for r in routes],
        [{"id": s.id, "label": format_manual_db_source_label(s)} for s in db_sources],
    )


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

        manual_route_entries, manual_db_source_entries = _manual_link_entries(container)
        rows.append(
            {
                "container": container,
                "webtob_connector_summary": ", ".join(connector_parts),
                "manual_route_entries": manual_route_entries,
                "manual_db_source_entries": manual_db_source_entries,
            }
        )
    return rows


TOMCAT_CONTAINER_SORT_LOOKUPS = {
    "hostname": "asset__hostname",
    "ip": "asset__primary_ip",
    "instance_name": "source__instance_name",
    "container": "name",
    "listen_port": "listen_port",
    "ssl_port": "ssl_port",
    "service_name": "service__name",
}


def get_tomcat_container_queryset(request):
    """JeusContainer 모델은 JEUS와 공유하지만(was/parsers.py의 parse_tomcat 참고) 화면은
    kind=jeus/jeus6 목록과 완전히 분리한다 - Tomcat 설정엔 WebToB 연결 개념이 없고
    node_name도 hostname과 항상 같은 값이라(was/parsers.py) JEUS 목록의 "Node"/"WebToB 연결"
    컬럼이 Tomcat에선 의미가 없다. 대신 이 화면엔 Tomcat만의 값인 데이터소스 목록을 보여준다
    (get_jeus_container_queryset와 동일하게 검색 필터가 own 필드/forward FK만 참조해
    .distinct() 불필요)."""
    queryset = (
        JeusContainer.objects.filter(source__kind=WasConfigSource.Kind.TOMCAT)
        .select_related("source__asset", "asset", "service")
        .defer("source__raw_content")
        .prefetch_related("data_sources", "manual_routes", "manual_db_sources")
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__asset__hostname__icontains=q)
            | Q(source__instance_name__icontains=q)
            | Q(asset__hostname__icontains=q)
            | Q(name__icontains=q)
            | Q(service__name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = TOMCAT_CONTAINER_SORT_LOOKUPS.get(sort_key, "asset__hostname")

    return queryset.order_by(f"{direction}{lookup}")


def build_tomcat_container_rows(containers):
    """데이터소스(JeusDataSource)는 컨테이너 하나에 여러 개씩 걸릴 수 있어(M2M) 표 한 칸에
    요약 문자열로 모아준다 - build_jeus_container_rows의 webtob_connector_summary와 같은 패턴
    (Tomcat엔 WebToB 연결이 없는 대신 데이터소스가 이 화면에서 의미 있는 관계형 값)."""
    rows = []
    for container in containers:
        data_source_summary = ", ".join(ds.data_source_id for ds in container.data_sources.all())
        manual_route_entries, manual_db_source_entries = _manual_link_entries(container)
        rows.append(
            {
                "container": container,
                "data_source_summary": data_source_summary,
                "manual_route_entries": manual_route_entries,
                "manual_db_source_entries": manual_db_source_entries,
            }
        )
    return rows


def get_service_labels_for_assets(asset_ids):
    """asset.id -> 그 asset에 연결된 WEB vhost/WAS 컨테이너들의 서비스명 목록(중복 제거,
    이름순) + Asset.manual_services(수기 보정, 아래 참고)의 합집합. vhost/컨테이너의 service
    FK는 여전히 단일값이지만(WebtobVhost.service 등 참고), 한 asset에 서로 다른 서비스의
    vhost/컨테이너가 같이 떠 있으면 자연히 계산값 라벨이 여러 개 모인다 - 매번 역추적해서
    계산하지 저장하지 않는다(topology.py의 build_service_topology_graph와 같은 원칙: 캐시로
    저장하지 않아 SystemHost 통짜교체 사고나 WebServiceDomain.service_name 비정규화 같은
    어긋남 위험이 아예 없음). values_list로 own 필드/forward FK 컬럼만 뽑으므로 TextField/
    JSONField가 SELECT에 안 끼어 NCLOB distinct 이슈도 없다.

    이 역추적 경로(WebToB<->JEUS 커넥터, hostname 매칭 등)가 끊기면 라벨이 아예 안 뜨는
    "구멍"이 생길 수 있어(예: WEB/WAS가 없는 DB 전용 서버), 사람이 직접 등록하는
    manual_services를 계산값과 합쳐서(대체가 아니라 보충) 같이 보여준다."""
    asset_ids = [aid for aid in asset_ids if aid is not None]
    if not asset_ids:
        return {}

    labels_by_asset = defaultdict(set)
    for model in (WebtobVhost, ApacheVhost, NginxVhost):
        rows = model.objects.filter(
            source__asset_id__in=asset_ids, service__isnull=False
        ).values_list("source__asset_id", "service__name")
        for asset_id, name in rows:
            labels_by_asset[asset_id].add(name)

    for asset_id, name in JeusContainer.objects.filter(
        asset_id__in=asset_ids, service__isnull=False
    ).values_list("asset_id", "service__name"):
        labels_by_asset[asset_id].add(name)

    for asset_id, name in Asset.objects.filter(
        id__in=asset_ids, manual_services__isnull=False
    ).values_list("id", "manual_services__name"):
        labels_by_asset[asset_id].add(name)

    return {asset_id: sorted(names) for asset_id, names in labels_by_asset.items()}


def get_service_labels_for_system_hosts(host_ids):
    """SystemHost.id -> 그 물리 호스트에 떠있는 VM들이 매칭된 asset들의 서비스 라벨(계산형,
    get_service_labels_for_assets와 동일 원칙) + SystemHost.manual_services(수기 보정)의
    합집합. 호스트 하나에 서로 다른 서비스의 VM이 같이 떠 있으면 자연히 계산값 라벨이 여러
    개 모인다. VM<->asset 매칭이 실패하거나 아직 VM push 자체가 없으면 계산값이 하나도 안
    나오는 구멍이 생길 수 있어, manual_services로 직접 보정할 수 있게 한다."""
    host_ids = [hid for hid in host_ids if hid is not None]
    if not host_ids:
        return {}

    host_to_assets = defaultdict(set)
    all_asset_ids = set()
    for host_id, asset_id in SystemVm.objects.filter(
        host_id__in=host_ids, asset__isnull=False
    ).values_list("host_id", "asset_id"):
        host_to_assets[host_id].add(asset_id)
        all_asset_ids.add(asset_id)

    asset_labels = get_service_labels_for_assets(all_asset_ids)
    result = defaultdict(set)
    for host_id, asset_ids in host_to_assets.items():
        for asset_id in asset_ids:
            result[host_id].update(asset_labels.get(asset_id, []))

    for host_id, name in SystemHost.objects.filter(
        id__in=host_ids, manual_services__isnull=False
    ).values_list("id", "manual_services__name"):
        result[host_id].add(name)

    return {host_id: sorted(names) for host_id, names in result.items()}


def get_service_labels_for_db_instances(instance_ids):
    """DbInstance.id -> 이 인스턴스를 참조하는 JeusDataSource의 컨테이너들이 속한 서비스
    라벨 목록(계산형, get_service_labels_for_assets와 동일 원칙 - topology.py가 JEUS<->DB
    엣지를 만들 때 따라가는 것과 같은 경로: JeusDataSource.db_instance). 인스턴스 하나를
    서로 다른 서비스의 컨테이너가 공유하면 자연히 라벨이 여러 개 모인다. 수기 보정은
    DbInstance가 아니라 DbConfigSource에 달려있다(get_service_labels_for_db_config_sources
    참고 - DbInstance는 push마다 통짜 교체돼 직접 필드를 못 붙임) - 인스턴스 단위 계산값이
    필요할 때만 이 함수를 쓴다."""
    instance_ids = [iid for iid in instance_ids if iid is not None]
    if not instance_ids:
        return {}

    labels_by_instance = defaultdict(set)
    for instance_id, name in JeusDataSource.objects.filter(
        db_instance_id__in=instance_ids, containers__service__isnull=False
    ).values_list("db_instance_id", "containers__service__name"):
        labels_by_instance[instance_id].add(name)
    return {iid: sorted(names) for iid, names in labels_by_instance.items()}


def get_service_labels_for_db_config_sources(source_ids):
    """DbConfigSource.id -> 그 소스 산하 모든 인스턴스(RAC면 여러 개)의 서비스 라벨(계산형,
    get_service_labels_for_system_hosts와 동일 패턴 - 호스트->VM->자산 대신 소스->인스턴스)
    + DbConfigSource.manual_services(수기 보정)의 합집합. SID가 안 맞거나 WAS가 아직 이
    DB를 push하지 않았으면 계산값이 하나도 안 나오는 구멍이 생길 수 있어, manual_services로
    직접 보정할 수 있게 한다(RAC라도 인스턴스 단위가 아니라 소스 전체 단위 보정)."""
    source_ids = [sid for sid in source_ids if sid is not None]
    if not source_ids:
        return {}

    source_to_instances = defaultdict(set)
    all_instance_ids = set()
    for source_id, instance_id in DbInstance.objects.filter(source_id__in=source_ids).values_list(
        "source_id", "id"
    ):
        source_to_instances[source_id].add(instance_id)
        all_instance_ids.add(instance_id)

    instance_labels = get_service_labels_for_db_instances(all_instance_ids)
    result = defaultdict(set)
    for source_id, instance_ids in source_to_instances.items():
        for instance_id in instance_ids:
            result[source_id].update(instance_labels.get(instance_id, []))

    for source_id, name in DbConfigSource.objects.filter(
        id__in=source_ids, manual_services__isnull=False
    ).values_list("id", "manual_services__name"):
        result[source_id].add(name)

    return {source_id: sorted(names) for source_id, names in result.items()}


def build_rows(assets, dynamic_field_definitions):
    assets = list(assets)
    service_labels_by_asset = get_service_labels_for_assets([a.id for a in assets])

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
        rows.append(
            {
                "asset": asset,
                "hostfact": hostfact,
                "dynamic_cells": dynamic_cells,
                "service_labels": service_labels_by_asset.get(asset.id, []),
            }
        )

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


SYSTEM_HOST_SORT_LOOKUPS = {
    "source_name": "source__name",
    "name": "name",
    "kind": "source__kind",
    "vm_count": "vm_count",
    "last_pushed_at": "source__last_pushed_at",
}


def get_system_host_queryset(request):
    # extra/raw_response(JSONField, Oracle에서 대용량으로 다뤄질 수 있음)는 목록에서 안 쓰므로
    # defer. 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없으므로(vm_count의
    # Count(distinct=True) 자체는 annotate라 검색 결과 행 중복과는 무관) .distinct()는 불필요.
    queryset = (
        SystemHost.objects.select_related("source")
        .defer("extra", "source__raw_response")
        .annotate(vm_count=Count("vms", distinct=True))
        .prefetch_related("field_values__field_definition", "vms")
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(external_id__icontains=q)
            | Q(source__name__icontains=q)
            | _kind_search_q(SystemSource.Kind, "source__kind", q)
        )

    sort = _request_param(request, "sort", "ordering", default="name")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = SYSTEM_HOST_SORT_LOOKUPS.get(sort_key, "name")

    return queryset.order_by(f"{direction}{lookup}")


def get_system_host_dynamic_field_definitions():
    """SystemHost 목록 컬럼으로 노출하는 필드 정의(AUTO+MANUAL 둘 다) - facts의
    get_dynamic_field_definitions()와 같은 목적, systems 앱 전용 모델(SystemHostFieldDefinition)
    기준. FIXED가 없어 별도 exclude는 불필요."""
    return (
        SystemHostFieldDefinition.objects.filter(is_visible=True)
        .prefetch_related("choices")
        .order_by("sort_order", "id")
    )


def build_system_host_rows(hosts, dynamic_field_definitions):
    """자산 목록의 build_rows()와 같은 패턴 - 고정 컬럼(이름/종류/VM 수)에 admin이 등록한
    동적 컬럼(AUTO/MANUAL)을 이어붙인다. 정렬은 아직 지원하지 않음(값이 EAV 테이블에 있어
    자산 목록처럼 Subquery 정렬이 필요한데, 필요해지면 get_asset_queryset의 방식을 그대로
    가져오면 됨).

    kind=physical 호스트는 AUTO 필드도 is_manual=True로 취급해 편집 가능하게 만든다 - AUTO는 push로
    들어온 extra에서 값을 뽑는 게 전제인데 수기 등록 호스트는 애초에 push 자체가 없어
    extra가 항상 비어있다. 이 kind는 sync_host_fields()가(=AUTO 값 자동 채움) 절대 호출되지
    않으므로 사람이 입력한 값이 다음 push에 덮어써질 위험도 없다 - 그래서 라벨/필드 정의를
    vCenter/Nutanix와 그대로 공유하면서 물리 행에서만 입력 UI를 열어줄 수 있다(field
    definition을 kind별로 중복 등록할 필요가 없어짐). vCenter/Nutanix 행은 지금처럼 AUTO는
    읽기 전용 유지(수정해봐야 다음 push에 조용히 덮어써져 혼란만 커짐)."""
    hosts = list(hosts)
    service_labels_by_host = get_service_labels_for_system_hosts([h.id for h in hosts])

    rows = []
    for host in hosts:
        values_by_field_id = {}
        for value in host.field_values.all():
            candidates = (value.value_text, value.value_number, value.value_date)
            values_by_field_id[value.field_definition_id] = next(
                (v for v in candidates if v not in (None, "")), None
            )

        dynamic_cells = [
            {
                "value": values_by_field_id.get(fd.id),
                "field_id": fd.id,
                "label": fd.label,
                "is_manual": fd.source == SystemHostFieldDefinition.Source.MANUAL
                or host.source.kind == SystemSource.Kind.PHYSICAL,
                "value_type": fd.value_type,
            }
            for fd in dynamic_field_definitions
        ]
        rows.append(
            {
                "host": host,
                "dynamic_cells": dynamic_cells,
                "service_labels": service_labels_by_host.get(host.id, []),
            }
        )
    return rows


def build_system_host_vm_entries(vms, os_dynamic_field_definitions):
    """물리 호스트 상세 화면의 "이 장비에 떠있는 OS(VM)" 표 - 자산관리 관점에서 "이 시스템에
    어떤 OS가 떠있나"를 보려는 목적이라, VM 자신의 하드웨어 정보(전원 상태/vCPU/디스크/NIC
    등)가 아니라 OS 목록에 이미 선언된 컬럼(고정 Hostname/IP/OS + admin이 등록한 동적 필드)을
    그대로 재사용해서 보여준다 - build_rows()와 같은 값을 자산 하나짜리로 재사용. 자산
    매칭이 안 된 VM은 보여줄 OS 정보 자체가 없으므로 hostname만 표시."""
    asset_ids = [vm.asset_id for vm in vms if vm.asset_id]
    assets = (
        Asset.objects.filter(id__in=asset_ids)
        .select_related("hostfact")
        .prefetch_related(
            Prefetch("hostfact__values", queryset=HostFactValue.objects.select_related("field_definition"))
        )
        if asset_ids
        else Asset.objects.none()
    )
    asset_rows_by_id = {r["asset"].id: r for r in build_rows(assets, os_dynamic_field_definitions)}

    entries = []
    for vm in vms:
        row = asset_rows_by_id.get(vm.asset_id) if vm.asset_id else None
        entries.append({"matched": row is not None, "row": row, "name": vm.hostname or vm.name})
    return entries


def get_system_hosts_for_vms(vms):
    """자산 상세의 "연결된 시스템" 섹션용 - VM들이 속한 SystemHost를 vm_count까지 annotate해서
    가져온다(목록 화면과 동일한 값을 보여주기 위해 get_system_host_queryset과 같은 annotate).
    extra/source__raw_response(JSONField→Oracle NCLOB)도 get_system_host_queryset과 동일하게
    defer - annotate()가 select_related로 끌려온 이 컬럼들까지 GROUP BY에 포함시켜
    ORA-00932(inconsistent datatypes: expected - got NCLOB)로 실제 폐쇄망에서 500이 났음
    (로컬 Postgres는 이 제약이 없어 재현 안 됨)."""
    host_ids = [vm.host_id for vm in vms if vm.host_id]
    if not host_ids:
        return SystemHost.objects.none()
    return (
        SystemHost.objects.filter(id__in=host_ids)
        .select_related("source")
        .defer("extra", "source__raw_response")
        .annotate(vm_count=Count("vms", distinct=True))
        .prefetch_related("field_values__field_definition")
    )


DB_CONFIG_SORT_LOOKUPS = {
    "db_unique_name": "db_unique_name",
    "kind": "kind",
    "db_name": "db_name",
    "database_role": "database_role",
    "open_mode": "open_mode",
    "hostname": "asset__hostname",
    "instance_count": "instance_count",
    "last_changed_at": "last_changed_at",
    "last_pushed_at": "last_pushed_at",
}


def get_db_config_queryset(request):
    # raw_content(TextField)/extra(JSONField)는 둘 다 Oracle에서 NCLOB이라 목록에서 안 쓰는
    # 이 화면은 defer로 뺀다 - webconfig/was의 get_*_queryset과 동일한 이유. q 필터가
    # instances(to-many)를 참조해 .distinct()가 필요한데, defer 없이 걸면 annotate의
    # GROUP BY/DISTINCT에 NCLOB 컬럼이 끌려들어가 ORA-00932가 난다(CLAUDE.md "환경" 참고).
    queryset = (
        DbConfigSource.objects.select_related("asset")
        .defer("raw_content", "extra")
        .annotate(
            instance_count=Count("instances", distinct=True),
            last_changed_at=Max("revisions__detected_at"),
        )
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(db_unique_name__icontains=q)
            | Q(db_name__icontains=q)
            | Q(asset__hostname__icontains=q)
            | Q(instances__instance_name__icontains=q)
            | Q(instances__host_name__icontains=q)
        ).distinct()

    sort = _request_param(request, "sort", "ordering", default="db_unique_name")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = DB_CONFIG_SORT_LOOKUPS.get(sort_key, "db_unique_name")

    return queryset.order_by(f"{direction}{lookup}")


def get_db_config_dynamic_field_definitions():
    """DbConfigSource 목록 컬럼으로 노출하는 필드 정의(AUTO+MANUAL 둘 다) - systems의
    get_system_host_dynamic_field_definitions()와 같은 목적, database 앱 전용 모델
    (DbConfigSourceFieldDefinition) 기준."""
    return (
        DbConfigSourceFieldDefinition.objects.filter(is_visible=True)
        .prefetch_related("choices")
        .order_by("sort_order", "id")
    )


def build_db_config_rows(sources, dynamic_field_definitions):
    """DB 목록의 build_system_host_rows()와 같은 패턴 - 고정 컬럼(db_unique_name/종류/DB명/
    Role/OpenMode/인스턴스 수)에 admin이 등록한 동적 컬럼(AUTO/MANUAL)을 이어붙인다."""
    sources = list(sources)
    service_labels_by_source = get_service_labels_for_db_config_sources([s.id for s in sources])

    rows = []
    for source in sources:
        values_by_field_id = {}
        for value in source.field_values.all():
            candidates = (value.value_text, value.value_number, value.value_date)
            values_by_field_id[value.field_definition_id] = next(
                (v for v in candidates if v not in (None, "")), None
            )

        dynamic_cells = [
            {
                "value": values_by_field_id.get(fd.id),
                "field_id": fd.id,
                "label": fd.label,
                "is_manual": fd.source == DbConfigSourceFieldDefinition.Source.MANUAL,
                "value_type": fd.value_type,
            }
            for fd in dynamic_field_definitions
        ]
        rows.append(
            {
                "source": source,
                "dynamic_cells": dynamic_cells,
                "service_labels": service_labels_by_source.get(source.id, []),
            }
        )
    return rows


DB_INSTANCE_SORT_LOOKUPS = {
    "db_unique_name": "source__db_unique_name",
    "hostname": "asset__hostname",
    "ip": "asset__primary_ip",
    "instance_name": "instance_name",
    "instance_number": "instance_number",
    "status": "status",
    "version": "version",
    "listener_port": "listener_port",
}


def get_db_instance_queryset(request):
    # 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없으므로(중복 행이 생길 수
    # 없음) .distinct()가 애초에 불필요 - WebToB/Apache/Nginx vhost 목록과 동일 원칙.
    # source__raw_content/source__extra(Oracle NCLOB)는 이 화면에서 안 쓰므로 defer.
    queryset = (
        DbInstance.objects.select_related("source", "asset")
        .defer("extra", "source__raw_content", "source__extra")
    )

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__db_unique_name__icontains=q)
            | Q(asset__hostname__icontains=q)
            | Q(host_name__icontains=q)
            | Q(instance_name__icontains=q)
        )

    sort = _request_param(request, "sort", "ordering", default="hostname")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = DB_INSTANCE_SORT_LOOKUPS.get(sort_key, "instance_name")

    return queryset.order_by(f"{direction}{lookup}")


def get_db_config_history_queryset(request):
    queryset = DbConfigSourceRevision.objects.select_related("source__asset")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(source__db_unique_name__icontains=q) | Q(source__asset__hostname__icontains=q)
        )

    return queryset.order_by("-detected_at")
