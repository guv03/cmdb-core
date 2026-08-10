from django.utils import timezone

from facts.dynamic_fields import coerce_fact_value, extract_json_path, resolve_field_path
from facts.models import FactChangeHistory, FactFieldDefinition, HostFactValue


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

# FactChangeHistory 표시용 라벨. FIXED 컬럼은 FactFieldDefinition 행이 없어 admin에서
# 라벨을 관리할 수 없으므로 여기 고정해둔다(AUTO/MANUAL 필드는 FactFieldDefinition.label 사용).
FIXED_FIELD_LABELS = {
    "os_family": "OS Family",
    "os_version": "OS Version",
    "source_platform": "Source Platform",
    "vm_uuid": "VM UUID",
    "cluster_name": "Cluster",
    "power_state": "Power State",
    "num_cpu": "CPU 수",
    "memory_mb": "메모리(MB)",
}


def compute_fixed_values(raw_facts: dict) -> dict:
    """push 시 HostFact 고정 컬럼에 바로 반영할 값을 FIXED_FIELD_EXTRACTORS로 뽑는다.
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


def _display(value) -> str:
    return "" if value is None else str(value)


def _typed_display(typed: dict) -> str:
    """value_text/value_number/value_date 중 실제로 채워진 하나만 문자열로 변환 - 0이나
    빈 문자열처럼 falsy하지만 유효한 값도 놓치지 않도록 truthy 체크(or)가 아니라 None
    여부로만 판단한다."""
    if typed["value_text"] is not None:
        return _display(typed["value_text"])
    if typed["value_number"] is not None:
        return _display(typed["value_number"])
    return _display(typed["value_date"])


def record_fact_changes(host_fact, raw_facts: dict, fixed_values: dict) -> None:
    """webconfig/was의 *Revision과 동일한 취지 - 이미 존재하는 자산의 AUTO/FIXED 필드 값이
    이번 push로 실제로 바뀐 것만 FactChangeHistory에 남긴다. 값 자체는 이 함수가 건드리지
    않는다 - FIXED는 호출부(facts/views.py)가, AUTO는 sync_dynamic_fields가 각각 반영하므로
    여기선 push 전(기존 DB 값) vs push로 들어온 값만 비교해서 기록만 한다. 신규 자산(첫
    push)은 "변경"이 아니라 호출부에서 이 함수 자체를 안 부른다.

    뭔가 하나라도 실제로 바뀌면 Asset.last_changed_at도 같이 갱신한다 - 예전엔 승인 시점에
    apply_pending_change()가 이 값을 갱신했는데, 승인 절차가 없어진 지금은 여기가 그 역할을
    대신한다(대시보드 "최근 변경일" 컬럼, CLAUDE.md "대시보드" 참고)."""
    asset = host_fact.asset
    changed = False

    for key, (extractor, default) in FIXED_FIELD_EXTRACTORS.items():
        old_value = getattr(host_fact, key, None)
        new_value = fixed_values.get(key)
        if _display(old_value) == _display(new_value):
            continue
        FactChangeHistory.objects.create(
            asset=asset,
            field_key=key,
            field_label=FIXED_FIELD_LABELS[key],
            old_value=_display(old_value),
            new_value=_display(new_value),
        )
        changed = True

    for field_definition in FactFieldDefinition.objects.filter(source=FactFieldDefinition.Source.AUTO):
        path = resolve_field_path(field_definition, host_fact.os_family)
        raw_value = extract_json_path(raw_facts, path)
        incoming = coerce_fact_value(raw_value, field_definition.value_type)

        value_row = HostFactValue.objects.filter(
            host_fact=host_fact, field_definition=field_definition
        ).first()
        applied = (
            {"value_text": value_row.value_text, "value_number": value_row.value_number, "value_date": value_row.value_date}
            if value_row is not None
            else {"value_text": None, "value_number": None, "value_date": None}
        )

        if incoming == applied:
            continue

        FactChangeHistory.objects.create(
            asset=asset,
            field_key=field_definition.key,
            field_label=field_definition.label,
            old_value=_typed_display(applied),
            new_value=_typed_display(incoming),
        )
        changed = True

    if changed:
        asset.last_changed_at = timezone.now()
        asset.save(update_fields=["last_changed_at"])
