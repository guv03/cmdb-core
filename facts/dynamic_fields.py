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
        if isinstance(raw_value, str):
            # 문자열은 파이썬 진위값으로 판단하면 "false"도 비어있지 않아 항상 True가 되므로 별도 처리.
            is_true = raw_value.strip().lower() in ("true", "1", "yes", "y", "예")
        else:
            is_true = bool(raw_value)
        return {**empty, "value_text": "true" if is_true else "false"}

    # TEXT, CHOICE (선택형도 저장은 텍스트와 동일 — 허용 값인지 확인은 is_valid_choice()에서 별도로 함)
    return {**empty, "value_text": str(raw_value)}


def is_valid_choice(field_definition: FactFieldDefinition, raw_value) -> bool:
    """CHOICE 타입이 아니거나 값이 비어있으면 항상 통과. CHOICE면 등록된 선택지인지 확인."""
    if field_definition.value_type != FactFieldDefinition.ValueType.CHOICE:
        return True
    if raw_value is None:
        return True
    return field_definition.choices.filter(value=str(raw_value)).exists()


def sync_dynamic_fields(host_fact: HostFact, exclude_keys: set[str] | None = None) -> None:
    # MANUAL 필드는 raw_facts에서 추출할 값이 없어 push 때마다 덮어쓰면 수기 입력값이 사라진다.
    field_definitions = FactFieldDefinition.objects.filter(source=FactFieldDefinition.Source.AUTO)
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
