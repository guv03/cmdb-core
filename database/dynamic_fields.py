from facts.dynamic_fields import coerce_fact_value, extract_json_path
from database.models import DbConfigSource, DbConfigSourceFieldDefinition, DbConfigSourceFieldValue


def resolve_source_field_path(field_definition: DbConfigSourceFieldDefinition, kind: str) -> str:
    """AUTO 컬럼의 실제 추출 경로. kind_key_overrides에 해당 kind가 있으면 그 경로, 없으면
    key를 그대로 씀 - systems.dynamic_fields.resolve_host_field_path와 같은 패턴."""
    overrides = field_definition.kind_key_overrides or {}
    return overrides.get(kind, field_definition.key)


def sync_source_fields(source: DbConfigSource) -> None:
    """push 시점에 등록된 AUTO DbConfigSourceFieldDefinition을 이 소스의 extra에서 뽑아
    DbConfigSourceFieldValue로 채운다. MANUAL 필드는 extra와 무관한 사람 입력값이라 push
    때마다 덮어쓰면 안 되므로 대상에서 제외."""
    for field_definition in DbConfigSourceFieldDefinition.objects.filter(
        source=DbConfigSourceFieldDefinition.Source.AUTO
    ):
        path = resolve_source_field_path(field_definition, source.kind)
        raw_value = extract_json_path(source.extra, path)
        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        DbConfigSourceFieldValue.objects.update_or_create(
            source=source, field_definition=field_definition, defaults=defaults
        )


def backfill_source_field(field_definition: DbConfigSourceFieldDefinition) -> int:
    """기존 DbConfigSource.extra에서 field_definition 값을 소급 추출해 채운다. 갱신된 소스
    수를 반환 - systems.dynamic_fields.backfill_host_field와 같은 패턴."""
    updated = 0
    for source in DbConfigSource.objects.all():
        path = resolve_source_field_path(field_definition, source.kind)
        raw_value = extract_json_path(source.extra, path)
        defaults = coerce_fact_value(raw_value, field_definition.value_type)
        DbConfigSourceFieldValue.objects.update_or_create(
            source=source, field_definition=field_definition, defaults=defaults
        )
        updated += 1
    return updated
