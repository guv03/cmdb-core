from dataclasses import dataclass

import openpyxl
from django.db.models import Prefetch
from django.utils import timezone

from core.models import Asset
from core.reconciliation import normalize_hostname
from facts.dynamic_fields import coerce_fact_value
from facts.models import FactFieldDefinition, HostFactValue

HOSTNAME_HEADER = "hostname"
MAX_ROWS = 2000


class ImportFileError(Exception):
    """헤더가 잘못됐거나 컬럼을 매칭할 수 없는 등, 파일 자체를 거부해야 하는 경우."""


@dataclass
class PendingUpdate:
    row_number: int
    asset_id: int
    hostname: str
    field_id: int
    field_label: str
    old_value: str
    new_value: str


@dataclass
class InvalidCell:
    row_number: int
    hostname: str
    field_label: str
    raw_value: str


@dataclass
class ImportResult:
    updates: list[PendingUpdate]
    unmatched_hostnames: list[tuple[int, str]]
    invalid_cells: list[InvalidCell]


def _manual_fields_by_label() -> dict[str, FactFieldDefinition]:
    manual_fields = list(
        FactFieldDefinition.objects.filter(
            source=FactFieldDefinition.Source.MANUAL, is_visible=True
        )
    )
    labels = [fd.label for fd in manual_fields]
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    if duplicate_labels:
        raise ImportFileError(
            "다음 라벨을 쓰는 수기 입력 필드가 여러 개 등록돼 있어 엑셀 헤더와 매칭할 수 없습니다: "
            f"{', '.join(duplicate_labels)}. admin에서 라벨을 정리한 뒤 다시 시도해주세요."
        )
    return {fd.label: fd for fd in manual_fields}


def _current_value_display(host_fact, field_definition: FactFieldDefinition) -> str:
    if host_fact is None:
        return ""
    value = next(
        (v for v in host_fact.values.all() if v.field_definition_id == field_definition.id), None
    )
    if value is None:
        return ""
    for candidate in (value.value_text, value.value_number, value.value_date):
        if candidate not in (None, ""):
            return str(candidate)
    return ""


def parse_manual_field_workbook(uploaded_file) -> ImportResult:
    try:
        workbook = openpyxl.load_workbook(uploaded_file, data_only=True, read_only=True)
    except Exception as exc:  # openpyxl은 손상 파일에 다양한 예외를 던짐
        raise ImportFileError(f"엑셀 파일을 열 수 없습니다: {exc}") from exc

    worksheet = workbook.active
    rows_iter = worksheet.iter_rows(values_only=True)

    header = next(rows_iter, None)
    if not header or str(header[0] or "").strip() != HOSTNAME_HEADER:
        raise ImportFileError(f"첫 번째 컬럼 헤더는 '{HOSTNAME_HEADER}'이어야 합니다.")

    fields_by_label = _manual_fields_by_label()

    column_fields: list[FactFieldDefinition | None] = []
    unknown_headers = []
    for col_header in header[1:]:
        col_header = str(col_header).strip() if col_header is not None else ""
        if not col_header:
            column_fields.append(None)
            continue
        field_definition = fields_by_label.get(col_header)
        if field_definition is None:
            unknown_headers.append(col_header)
        column_fields.append(field_definition)

    if unknown_headers:
        raise ImportFileError(
            "다음 컬럼은 등록된 수기 입력 필드와 매칭되지 않습니다: " + ", ".join(unknown_headers)
        )

    choice_values_by_field_id = {
        fd.id: set(fd.choices.values_list("value", flat=True))
        for fd in column_fields
        if fd is not None and fd.value_type == FactFieldDefinition.ValueType.CHOICE
    }

    raw_rows = []
    hostnames = set()
    for row_number, row in enumerate(rows_iter, start=2):
        if row is None or all(cell in (None, "") for cell in row):
            continue
        hostname = normalize_hostname(str(row[0])) if row[0] is not None else ""
        if not hostname:
            continue
        hostnames.add(hostname)
        raw_rows.append((row_number, hostname, row[1:]))

        if len(raw_rows) > MAX_ROWS:
            raise ImportFileError(f"한 번에 업로드 가능한 최대 행 수({MAX_ROWS}건)를 초과했습니다.")

    assets_by_hostname = {
        asset.hostname: asset
        for asset in Asset.objects.filter(hostname__in=hostnames)
        .select_related("hostfact")
        .prefetch_related(
            Prefetch(
                "hostfact__values", queryset=HostFactValue.objects.select_related("field_definition")
            )
        )
    }

    updates: list[PendingUpdate] = []
    unmatched_hostnames: list[tuple[int, str]] = []
    invalid_cells: list[InvalidCell] = []

    for row_number, hostname, values in raw_rows:
        asset = assets_by_hostname.get(hostname)
        if asset is None:
            unmatched_hostnames.append((row_number, hostname))
            continue

        host_fact = getattr(asset, "hostfact", None)

        for field_definition, cell_value in zip(column_fields, values):
            if field_definition is None or cell_value in (None, ""):
                continue

            defaults = coerce_fact_value(cell_value, field_definition.value_type)
            parse_failed = (
                field_definition.value_type
                in (FactFieldDefinition.ValueType.NUMBER, FactFieldDefinition.ValueType.DATE)
                and all(v is None for v in defaults.values())
            )
            invalid_choice = field_definition.value_type == FactFieldDefinition.ValueType.CHOICE and (
                str(cell_value) not in choice_values_by_field_id.get(field_definition.id, set())
            )
            if parse_failed or invalid_choice:
                invalid_cells.append(
                    InvalidCell(
                        row_number=row_number,
                        hostname=hostname,
                        field_label=field_definition.label,
                        raw_value=str(cell_value),
                    )
                )
                continue

            updates.append(
                PendingUpdate(
                    row_number=row_number,
                    asset_id=asset.id,
                    hostname=hostname,
                    field_id=field_definition.id,
                    field_label=field_definition.label,
                    old_value=_current_value_display(host_fact, field_definition),
                    new_value=str(cell_value),
                )
            )

    return ImportResult(
        updates=updates, unmatched_hostnames=unmatched_hostnames, invalid_cells=invalid_cells
    )


def apply_updates(payload: list[dict]) -> tuple[int, int]:
    """미리보기에서 확정된 항목을 실제로 반영. (반영된 값 개수, 영향받은 자산 수)를 반환."""
    field_definitions = {
        fd.id: fd
        for fd in FactFieldDefinition.objects.filter(
            source=FactFieldDefinition.Source.MANUAL, is_visible=True
        )
    }
    asset_ids = {item["asset_id"] for item in payload}
    assets = {
        asset.id: asset
        for asset in Asset.objects.filter(id__in=asset_ids).select_related("hostfact")
    }

    changed_asset_ids = set()
    applied = 0
    for item in payload:
        field_definition = field_definitions.get(item["field_id"])
        asset = assets.get(item["asset_id"])
        if field_definition is None or asset is None:
            continue
        host_fact = getattr(asset, "hostfact", None)
        if host_fact is None:
            continue

        defaults = coerce_fact_value(item["new_value"], field_definition.value_type)
        HostFactValue.objects.update_or_create(
            host_fact=host_fact, field_definition=field_definition, defaults=defaults
        )
        changed_asset_ids.add(asset.id)
        applied += 1

    if changed_asset_ids:
        Asset.objects.filter(id__in=changed_asset_ids).update(last_changed_at=timezone.now())

    return applied, len(changed_asset_ids)
