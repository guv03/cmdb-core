from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from facts.models import FactFieldDefinition, HostFact, HostFactValue


def extract_json_path(data: dict, path: str):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def coerce_fact_value(raw_value, value_type: str) -> dict:
    """value_type에 맞는 컬럼 하나만 채운 dict를 반환. 변환 불가하면 전부 None."""
    empty = {"value_text": None, "value_number": None, "value_date": None}
    if raw_value is None:
        return empty

    if value_type == FactFieldDefinition.ValueType.NUMBER:
        try:
            return {**empty, "value_number": Decimal(str(raw_value))}
        except (InvalidOperation, ValueError, TypeError):
            return empty

    if value_type == FactFieldDefinition.ValueType.DATE:
        if isinstance(raw_value, date):
            return {**empty, "value_date": raw_value}
        try:
            return {**empty, "value_date": datetime.fromisoformat(str(raw_value)).date()}
        except ValueError:
            return empty

    if value_type == FactFieldDefinition.ValueType.BOOL:
        return {**empty, "value_text": "true" if raw_value else "false"}

    # TEXT (기본값)
    return {**empty, "value_text": str(raw_value)}


def sync_dynamic_fields(host_fact: HostFact, exclude_keys: set[str] | None = None) -> None:
    field_definitions = FactFieldDefinition.objects.all()
    if exclude_keys:
        field_definitions = field_definitions.exclude(key__in=exclude_keys)
    for field_definition in field_definitions:
        raw_value = extract_json_path(host_fact.raw_facts, field_definition.key)
        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        HostFactValue.objects.update_or_create(
            host_fact=host_fact, field_definition=field_definition, defaults=defaults
        )


def backfill_field(field_definition: FactFieldDefinition) -> int:
    """기존 HostFact.raw_facts에서 field_definition 값을 소급 추출해 채운다. 갱신된 호스트 수를 반환."""
    updated = 0
    for host_fact in HostFact.objects.all():
        raw_value = extract_json_path(host_fact.raw_facts, field_definition.key)
        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        HostFactValue.objects.update_or_create(
            host_fact=host_fact, field_definition=field_definition, defaults=defaults
        )
        updated += 1
    return updated
