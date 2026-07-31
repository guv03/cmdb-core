from django.utils import timezone

from facts.dynamic_fields import coerce_fact_value, extract_json_path, resolve_field_path
from facts.models import FactFieldDefinition, HostFactValue, PendingChange


def _extract_os_family(raw_facts: dict):
    return extract_json_path(raw_facts, "ansible_facts.os_family")


def _extract_os_version(raw_facts: dict):
    # Windows는 distribution_version이 커널 빌드번호("10.0.20348.0")라 사람이 읽는 버전이
    # 아니어서 distribution(마케팅명, "Microsoft Windows Server 2022 Standard")을 대신 쓴다.
    if _extract_os_family(raw_facts) == "Windows":
        return extract_json_path(raw_facts, "ansible_facts.distribution")
    return extract_json_path(raw_facts, "ansible_facts.distribution_version")


# fixed 필드 key -> (raw_facts에서 값을 뽑는 함수, 값이 없을 때 기본값)
FIXED_FIELD_EXTRACTORS = {
    "os_family": (_extract_os_family, ""),
    "os_version": (_extract_os_version, ""),
    "source_platform": (lambda raw: extract_json_path(raw, "hypervisor.source_platform"), None),
    "vm_uuid": (lambda raw: extract_json_path(raw, "hypervisor.vm_uuid"), None),
    "cluster_name": (lambda raw: extract_json_path(raw, "hypervisor.cluster_name"), None),
    "power_state": (lambda raw: extract_json_path(raw, "hypervisor.power_state"), None),
    "num_cpu": (lambda raw: extract_json_path(raw, "hypervisor.num_cpu"), None),
    "memory_mb": (lambda raw: extract_json_path(raw, "hypervisor.memory_mb"), None),
}


def compute_fixed_values(raw_facts: dict) -> dict:
    """신규/비승인 push 시 HostFact 고정 컬럼에 바로 반영할 값을 FIXED_FIELD_EXTRACTORS로 뽑는다.
    num_cpu/memory_mb는 AWX 인벤토리 매핑 누락 시 키가 없거나(None) 빈 문자열로 올 수 있어
    DB 저장 실패를 막기 위해 둘 다 None으로 정규화한다."""
    values = {}
    for key, (extractor, default) in FIXED_FIELD_EXTRACTORS.items():
        raw = extractor(raw_facts)
        if key in ("num_cpu", "memory_mb"):
            values[key] = raw if raw not in ("", None) else None
        else:
            values[key] = raw if raw is not None else default
    return values


def _typed_dict(value_text=None, value_number=None, value_date=None):
    return {"value_text": value_text, "value_number": value_number, "value_date": value_date}


def _applied_value(host_fact, field_definition: FactFieldDefinition) -> dict:
    if field_definition.source == FactFieldDefinition.Source.FIXED:
        raw = getattr(host_fact, field_definition.key, None)
        return coerce_fact_value(raw, field_definition.value_type)

    value_row = HostFactValue.objects.filter(
        host_fact=host_fact, field_definition=field_definition
    ).first()
    if value_row is None:
        return _typed_dict()
    return _typed_dict(value_row.value_text, value_row.value_number, value_row.value_date)


def _incoming_value(raw_facts: dict, field_definition: FactFieldDefinition, os_family: str) -> dict:
    if field_definition.source == FactFieldDefinition.Source.FIXED:
        extractor = FIXED_FIELD_EXTRACTORS[field_definition.key][0]
        raw = extractor(raw_facts)
    else:
        path = resolve_field_path(field_definition, os_family)
        raw = extract_json_path(raw_facts, path)
    return coerce_fact_value(raw, field_definition.value_type)


def stage_governed_changes(host_fact, ansible_facts: dict, hypervisor: dict) -> None:
    """승인 대상으로 지정된 필드 중 값이 바뀐 것을 PendingChange로 쌓는다. 실제 데이터는 건드리지 않는다."""
    raw_facts = {"ansible_facts": ansible_facts, "hypervisor": hypervisor}

    for field_definition in FactFieldDefinition.objects.filter(requires_approval=True):
        applied = _applied_value(host_fact, field_definition)
        incoming = _incoming_value(raw_facts, field_definition, host_fact.os_family)

        if incoming == applied:
            continue

        latest_pending = (
            PendingChange.objects.filter(
                asset=host_fact.asset,
                field_definition=field_definition,
                status=PendingChange.Status.PENDING,
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
            field_definition=field_definition,
            old_value_text=applied["value_text"],
            old_value_number=applied["value_number"],
            old_value_date=applied["value_date"],
            new_value_text=incoming["value_text"],
            new_value_number=incoming["value_number"],
            new_value_date=incoming["value_date"],
        )


def apply_pending_change(pending_change: PendingChange, decided_by: str) -> None:
    field_definition = pending_change.field_definition
    host_fact = pending_change.asset.hostfact
    new_value = _typed_dict(
        pending_change.new_value_text, pending_change.new_value_number, pending_change.new_value_date
    )

    if field_definition.source == FactFieldDefinition.Source.FIXED:
        default = FIXED_FIELD_EXTRACTORS[field_definition.key][1]
        if field_definition.value_type == FactFieldDefinition.ValueType.NUMBER:
            value = int(new_value["value_number"]) if new_value["value_number"] is not None else default
        elif field_definition.value_type == FactFieldDefinition.ValueType.DATE:
            value = new_value["value_date"] if new_value["value_date"] is not None else default
        else:
            value = new_value["value_text"] if new_value["value_text"] is not None else default
        setattr(host_fact, field_definition.key, value)
        host_fact.save(update_fields=[field_definition.key])
    else:
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
