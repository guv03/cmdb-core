from django.db.models import CharField, DateField, DecimalField, OuterRef, Prefetch, Q, Subquery

from core.models import Asset
from facts.models import FactFieldDefinition, HostFactValue, PendingChange

FIXED_COLUMNS = [
    {"key": "hostname", "label": "Hostname", "lookup": "hostname"},
    {"key": "primary_ip", "label": "IP", "lookup": "primary_ip"},
    {"key": "os_family", "label": "OS", "lookup": "hostfact__os_family"},
    {"key": "cluster_name", "label": "Cluster", "lookup": "hostfact__cluster_name"},
    {"key": "power_state", "label": "Power State", "lookup": "hostfact__power_state"},
    {"key": "last_seen_at", "label": "Last Seen", "lookup": "hostfact__last_seen_at"},
    {"key": "created_at", "label": "생성일", "lookup": "created_at"},
    {"key": "last_changed_at", "label": "최근 변경일", "lookup": "last_changed_at"},
]

_FIXED_LOOKUPS = {c["key"]: c["lookup"] for c in FIXED_COLUMNS}

_VALUE_FIELD_BY_TYPE = {
    FactFieldDefinition.ValueType.NUMBER: ("value_number", DecimalField()),
    FactFieldDefinition.ValueType.DATE: ("value_date", DateField()),
    FactFieldDefinition.ValueType.TEXT: ("value_text", CharField()),
    FactFieldDefinition.ValueType.BOOL: ("value_text", CharField()),
}


def get_dynamic_field_definitions():
    return FactFieldDefinition.objects.filter(is_visible=True).order_by("sort_order", "id")


def _request_param(request, *names, default=None):
    for name in names:
        value = request.GET.get(name)
        if value:
            return value
    return default


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
            if field_definition.is_searchable:
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

    columns = []
    for column in FIXED_COLUMNS:
        is_active = column["key"] == current_key
        next_sort = f"-{column['key']}" if is_active and not current_desc else column["key"]
        columns.append({**column, "is_active": is_active, "next_sort": next_sort})

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
                "field_id": field_definition.id,
            }
        )

    return columns


CHANGE_HISTORY_SORT_LOOKUPS = {
    "created_at": "created_at",
    "decided_at": "decided_at",
    "status": "status",
    "asset": "asset__hostname",
}


def get_change_history_queryset(request):
    queryset = PendingChange.objects.select_related("asset", "field_config")

    q = _request_param(request, "q", "search")
    if q:
        queryset = queryset.filter(
            Q(asset__hostname__icontains=q) | Q(field_config__label__icontains=q)
        )

    change_status = request.GET.get("status")
    if change_status:
        queryset = queryset.filter(status=change_status)

    sort = _request_param(request, "sort", "ordering", default="-created_at")
    direction = "-" if sort.startswith("-") else ""
    sort_key = sort.lstrip("-")
    lookup = CHANGE_HISTORY_SORT_LOOKUPS.get(sort_key, "created_at")

    return queryset.order_by(f"{direction}{lookup}")


def build_rows(assets, dynamic_field_definitions):
    rows = []
    for asset in assets:
        hostfact = getattr(asset, "hostfact", None)
        values_by_field_id = {}
        if hostfact is not None:
            for value in hostfact.values.all():
                values_by_field_id[value.field_definition_id] = (
                    value.value_text
                    if value.value_text is not None
                    else value.value_number if value.value_number is not None else value.value_date
                )

        dynamic_values = [values_by_field_id.get(fd.id) for fd in dynamic_field_definitions]
        rows.append({"asset": asset, "hostfact": hostfact, "dynamic_values": dynamic_values})

    return rows
