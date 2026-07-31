from facts.dynamic_fields import coerce_fact_value, extract_json_path
from systems.models import SystemHost, SystemHostFieldDefinition, SystemHostFieldValue


def resolve_host_field_path(field_definition: SystemHostFieldDefinition, kind: str) -> str:
    """AUTO 컬럼의 실제 추출 경로. kind_key_overrides에 해당 kind가 있으면 그 경로, 없으면
    (대부분의 필드는 늘 이 경우) key를 그대로 씀 - facts.dynamic_fields.resolve_field_path와
    같은 패턴."""
    overrides = field_definition.kind_key_overrides or {}
    return overrides.get(kind, field_definition.key)


def is_valid_choice(field_definition: SystemHostFieldDefinition, raw_value) -> bool:
    """CHOICE 타입이 아니거나 값이 비어있으면 항상 통과. CHOICE면 등록된 선택지인지 확인 -
    facts.dynamic_fields.is_valid_choice와 같은 패턴."""
    if field_definition.value_type != SystemHostFieldDefinition.ValueType.CHOICE:
        return True
    if raw_value is None:
        return True
    return field_definition.choices.filter(value=str(raw_value)).exists()


def sync_host_fields(host: SystemHost, kind: str) -> None:
    """push 시점에 등록된 AUTO SystemHostFieldDefinition을 이 호스트의 extra에서 뽑아
    SystemHostFieldValue로 채운다. MANUAL 필드는 extra와 무관한 사람 입력값이라 push 때마다
    덮어쓰면 안 되므로 대상에서 제외(facts의 sync_dynamic_fields와 같은 이유)."""
    for field_definition in SystemHostFieldDefinition.objects.filter(
        source=SystemHostFieldDefinition.Source.AUTO
    ):
        path = resolve_host_field_path(field_definition, kind)
        raw_value = extract_json_path(host.extra, path)
        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        SystemHostFieldValue.objects.update_or_create(
            host=host, field_definition=field_definition, defaults=defaults
        )


def backfill_host_field(field_definition: SystemHostFieldDefinition) -> int:
    """기존 SystemHost.extra에서 field_definition 값을 소급 추출해 채운다. 갱신된 호스트
    수를 반환 - facts.dynamic_fields.backfill_field와 같은 패턴."""
    updated = 0
    for host in SystemHost.objects.select_related("source"):
        path = resolve_host_field_path(field_definition, host.source.kind)
        raw_value = extract_json_path(host.extra, path)
        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        SystemHostFieldValue.objects.update_or_create(
            host=host, field_definition=field_definition, defaults=defaults
        )
        updated += 1
    return updated
