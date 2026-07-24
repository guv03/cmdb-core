from django.db import migrations

# key -> (기본 label, value_type). ApprovalFieldConfig에 이미 등록된 값이 있으면 그쪽 label/value_type로 덮어씀.
FIXED_FIELD_DEFAULTS = {
    "os_family": ("OS", "text"),
    "os_version": ("OS 버전", "text"),
    "source_platform": ("수집 출처", "text"),
    "vm_uuid": ("VM UUID", "text"),
    "cluster_name": ("클러스터명", "text"),
    "power_state": ("전원 상태", "text"),
    "num_cpu": ("CPU 수", "number"),
    "memory_mb": ("메모리(MB)", "number"),
}


def migrate_forward(apps, schema_editor):
    FactFieldDefinition = apps.get_model("facts", "FactFieldDefinition")
    ApprovalFieldConfig = apps.get_model("facts", "ApprovalFieldConfig")
    PendingChange = apps.get_model("facts", "PendingChange")

    for key, (label, value_type) in FIXED_FIELD_DEFAULTS.items():
        FactFieldDefinition.objects.get_or_create(
            key=key,
            defaults={
                "label": label,
                "value_type": value_type,
                "source": "fixed",
                "is_visible": False,
                "is_searchable": False,
                "sort_order": 0,
                "requires_approval": False,
            },
        )

    # (source_type, key) -> FactFieldDefinition.id. 이후 PendingChange 재연결에 재사용.
    resolved_field_definition_id = {}

    for config in ApprovalFieldConfig.objects.all():
        if config.source_type == "fixed":
            field_definition = FactFieldDefinition.objects.filter(key=config.key, source="fixed").first()
            if field_definition is None:
                continue
            field_definition.label = config.label
            field_definition.value_type = config.value_type
            field_definition.requires_approval = True
            field_definition.save(update_fields=["label", "value_type", "requires_approval"])
        else:
            field_definition = FactFieldDefinition.objects.filter(key=config.key).exclude(source="fixed").first()
            if field_definition is None:
                continue
            field_definition.requires_approval = True
            field_definition.save(update_fields=["requires_approval"])

        resolved_field_definition_id[(config.source_type, config.key)] = field_definition.id

    for pending_change in PendingChange.objects.select_related("field_config"):
        field_definition_id = resolved_field_definition_id.get(
            (pending_change.field_config.source_type, pending_change.field_config.key)
        )
        if field_definition_id is None:
            continue
        pending_change.field_definition_id = field_definition_id
        pending_change.save(update_fields=["field_definition"])


def migrate_backward(apps, schema_editor):
    FactFieldDefinition = apps.get_model("facts", "FactFieldDefinition")
    ApprovalFieldConfig = apps.get_model("facts", "ApprovalFieldConfig")
    PendingChange = apps.get_model("facts", "PendingChange")

    resolved_field_config_id = {}

    for field_definition in FactFieldDefinition.objects.filter(requires_approval=True):
        source_type = "fixed" if field_definition.source == "fixed" else "dynamic"
        config, _ = ApprovalFieldConfig.objects.get_or_create(
            source_type=source_type,
            key=field_definition.key,
            defaults={"label": field_definition.label, "value_type": field_definition.value_type},
        )
        resolved_field_config_id[field_definition.id] = config.id

    for pending_change in PendingChange.objects.filter(field_definition__isnull=False):
        field_config_id = resolved_field_config_id.get(pending_change.field_definition_id)
        if field_config_id is None:
            continue
        pending_change.field_config_id = field_config_id
        pending_change.save(update_fields=["field_config"])


class Migration(migrations.Migration):

    dependencies = [
        ('facts', '0005_factfielddefinition_requires_approval_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
