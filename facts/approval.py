from django.utils import timezone

from facts.dynamic_fields import coerce_fact_value, extract_json_path
from facts.models import ApprovalFieldConfig, FactFieldDefinition, HostFactValue, PendingChange

# fixed 필드 key -> (raw_facts 안의 dot-path, 값이 없을 때 기본값)
FIXED_FIELD_PATHS = {
    "os_family": ("ansible_facts.distribution", ""),
    "os_version": ("ansible_facts.distribution_version", ""),
    "source_platform": ("hypervisor.source_platform", None),
    "vm_uuid": ("hypervisor.vm_uuid", None),
    "cluster_name": ("hypervisor.cluster_name", None),
    "power_state": ("hypervisor.power_state", None),
    "num_cpu": ("hypervisor.num_cpu", None),
    "memory_mb": ("hypervisor.memory_mb", None),
}


def _typed_dict(value_text=None, value_number=None, value_date=None):
    return {"value_text": value_text, "value_number": value_number, "value_date": value_date}


def _applied_value(host_fact, config: ApprovalFieldConfig) -> dict:
    if config.source_type == ApprovalFieldConfig.SourceType.FIXED:
        raw = getattr(host_fact, config.key, None)
        return coerce_fact_value(raw, config.value_type)

    value_row = HostFactValue.objects.filter(
        host_fact=host_fact, field_definition__key=config.key
    ).first()
    if value_row is None:
        return _typed_dict()
    return _typed_dict(value_row.value_text, value_row.value_number, value_row.value_date)


def _incoming_value(raw_facts: dict, config: ApprovalFieldConfig) -> dict:
    if config.source_type == ApprovalFieldConfig.SourceType.FIXED:
        path = FIXED_FIELD_PATHS[config.key][0]
    else:
        path = config.key
    raw = extract_json_path(raw_facts, path)
    return coerce_fact_value(raw, config.value_type)


def stage_governed_changes(host_fact, ansible_facts: dict, hypervisor: dict) -> None:
    """승인 대상으로 지정된 필드 중 값이 바뀐 것을 PendingChange로 쌓는다. 실제 데이터는 건드리지 않는다."""
    raw_facts = {"ansible_facts": ansible_facts, "hypervisor": hypervisor}

    for config in ApprovalFieldConfig.objects.all():
        applied = _applied_value(host_fact, config)
        incoming = _incoming_value(raw_facts, config)

        if incoming == applied:
            continue

        latest_pending = (
            PendingChange.objects.filter(
                asset=host_fact.asset, field_config=config, status=PendingChange.Status.PENDING
            )
            .order_by("-created_at")
            .first()
        )
        if latest_pending is not None and incoming == _typed_dict(
            latest_pending.new_value_text, latest_pending.new_value_number, latest_pending.new_value_date
        ):
            continue

        PendingChange.objects.create(
            asset=host_fact.asset,
            field_config=config,
            old_value_text=applied["value_text"],
            old_value_number=applied["value_number"],
            old_value_date=applied["value_date"],
            new_value_text=incoming["value_text"],
            new_value_number=incoming["value_number"],
            new_value_date=incoming["value_date"],
        )


def apply_pending_change(pending_change: PendingChange, decided_by: str) -> None:
    config = pending_change.field_config
    host_fact = pending_change.asset.hostfact
    new_value = _typed_dict(
        pending_change.new_value_text, pending_change.new_value_number, pending_change.new_value_date
    )

    if config.source_type == ApprovalFieldConfig.SourceType.FIXED:
        default = FIXED_FIELD_PATHS[config.key][1]
        if config.value_type == FactFieldDefinition.ValueType.NUMBER:
            value = int(new_value["value_number"]) if new_value["value_number"] is not None else default
        elif config.value_type == FactFieldDefinition.ValueType.DATE:
            value = new_value["value_date"] if new_value["value_date"] is not None else default
        else:
            value = new_value["value_text"] if new_value["value_text"] is not None else default
        setattr(host_fact, config.key, value)
        host_fact.save(update_fields=[config.key])
    else:
        field_definition = FactFieldDefinition.objects.get(key=config.key)
        HostFactValue.objects.update_or_create(
            host_fact=host_fact, field_definition=field_definition, defaults=new_value
        )

    now = timezone.now()
    pending_change.status = PendingChange.Status.APPROVED
    pending_change.decided_at = now
    pending_change.decided_by = decided_by
    pending_change.save()

    pending_change.asset.last_changed_at = now
    pending_change.asset.save(update_fields=["last_changed_at"])


def reject_pending_change(pending_change: PendingChange, decided_by: str) -> None:
    pending_change.status = PendingChange.Status.REJECTED
    pending_change.decided_at = timezone.now()
    pending_change.decided_by = decided_by
    pending_change.save()
