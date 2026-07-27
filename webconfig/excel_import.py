from dataclasses import dataclass

import openpyxl
from django.http import HttpResponse

from core.reconciliation import normalize_hostname
from webconfig.models import WebConfigSource, WebServiceDomain, WebtobVhost

HOSTNAME_HEADER = "hostname"
VHOST_HEADER = "vhost"
DOMAIN_HEADER = "domain"
ALIASES_HEADER = "aliases"
SERVICE_NAME_HEADER = "서비스명"
VERSION_HEADER = "솔루션버전"
MAX_ROWS = 2000

# 도메인은 vhost 하나당 유일하지 않을 수 있어서(같은 도메인을 http/https vhost 두 개가
# 나눠 쓰는 경우가 실제로 있음, 예: vhost1/vhost1_ssl) 매칭 키로 못 쓴다. domain/aliases는
# 사람이 알아보기 위한 참고용 컬럼으로만 두고, 실제 매칭은 (hostname, vhost) 조합으로 한다
# - vhost 이름은 source당 유일(WebtobVhost의 unique constraint)이라 안전하다.
_KNOWN_EXTRA_HEADERS = {
    DOMAIN_HEADER: "domain",
    ALIASES_HEADER: "aliases",
    SERVICE_NAME_HEADER: "service_name",
    VERSION_HEADER: "version",
}


class ImportFileError(Exception):
    """헤더가 잘못됐거나 컬럼을 매칭할 수 없는 등, 파일 자체를 거부해야 하는 경우."""


@dataclass
class ServiceNameUpdate:
    row_number: int
    service_domain_id: int
    hostname: str
    vhost_name: str
    old_value: str
    new_value: str


@dataclass
class VersionUpdate:
    row_number: int
    source_id: int
    hostname: str
    old_value: str
    new_value: str


@dataclass
class VersionConflict:
    hostname: str
    row_numbers: list[int]
    values: list[str]


@dataclass
class UnmatchedRow:
    row_number: int
    hostname: str
    vhost_name: str


@dataclass
class ServiceImportResult:
    service_name_updates: list[ServiceNameUpdate]
    version_updates: list[VersionUpdate]
    version_conflicts: list[VersionConflict]
    unmatched_rows: list[UnmatchedRow]


def export_service_workbook() -> HttpResponse:
    """지금 서비스 조회 화면의 전체 데이터를 그대로 xlsx로 내려준다(검색 필터 무시 - 완전한
    사본을 줘야 재업로드할 때 행이 빠져서 헷갈리는 일이 없음). 헤더가 그대로 업로드 형식이라
    다운로드 → 몇 칸만 고쳐서 재업로드하는 흐름으로 쓰라고 만든 것."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "서비스"
    sheet.append(
        [HOSTNAME_HEADER, VHOST_HEADER, DOMAIN_HEADER, ALIASES_HEADER, SERVICE_NAME_HEADER, VERSION_HEADER]
    )

    rows = WebServiceDomain.objects.select_related("source", "source__asset").order_by(
        "source__asset__hostname", "domain"
    )
    for row in rows:
        sheet.append(
            [
                row.source.asset.hostname,
                row.vhost_name,
                row.domain,
                row.aliases,
                row.service_name,
                row.source.solution_version,
            ]
        )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="cmdb_services.xlsx"'
    workbook.save(response)
    return response


def parse_service_workbook(uploaded_file) -> ServiceImportResult:
    try:
        workbook = openpyxl.load_workbook(uploaded_file, data_only=True, read_only=True)
    except Exception as exc:  # openpyxl은 손상 파일에 다양한 예외를 던짐
        raise ImportFileError(f"엑셀 파일을 열 수 없습니다: {exc}") from exc

    worksheet = workbook.active
    rows_iter = worksheet.iter_rows(values_only=True)

    header = next(rows_iter, None)
    header_ok = (
        header
        and len(header) >= 2
        and str(header[0] or "").strip() == HOSTNAME_HEADER
        and str(header[1] or "").strip() == VHOST_HEADER
    )
    if not header_ok:
        raise ImportFileError(
            f"첫 번째/두 번째 컬럼 헤더는 '{HOSTNAME_HEADER}', '{VHOST_HEADER}'이어야 합니다."
        )

    column_roles: list[str | None] = []
    unknown_headers = []
    for col_header in header[2:]:
        col_header = str(col_header).strip() if col_header is not None else ""
        if not col_header:
            column_roles.append(None)
            continue
        role = _KNOWN_EXTRA_HEADERS.get(col_header)
        if role is None:
            unknown_headers.append(col_header)
        column_roles.append(role)

    if unknown_headers:
        raise ImportFileError("다음 컬럼을 인식할 수 없습니다: " + ", ".join(unknown_headers))

    service_name_col = column_roles.index("service_name") if "service_name" in column_roles else None
    version_col = column_roles.index("version") if "version" in column_roles else None

    raw_rows = []
    for row_number, row in enumerate(rows_iter, start=2):
        if row is None or all(cell in (None, "") for cell in row):
            continue
        hostname = normalize_hostname(str(row[0])) if row[0] is not None else ""
        vhost_name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if not hostname:
            continue
        raw_rows.append((row_number, hostname, vhost_name, row[2:]))

        if len(raw_rows) > MAX_ROWS:
            raise ImportFileError(f"한 번에 업로드 가능한 최대 행 수({MAX_ROWS}건)를 초과했습니다.")

    hostnames = {r[1] for r in raw_rows}
    service_domains = list(
        WebServiceDomain.objects.filter(source__asset__hostname__in=hostnames).select_related(
            "source", "source__asset"
        )
    )
    row_map = {(sd.source.asset.hostname, sd.vhost_name): sd for sd in service_domains}
    sources_by_id = {sd.source_id: sd.source for sd in service_domains}

    service_name_updates: list[ServiceNameUpdate] = []
    unmatched_rows: list[UnmatchedRow] = []
    # source_id -> 그 source에 매겨진 (row_number, new_value) 목록 - 솔루션버전은 source 단위값이라
    # 같은 호스트의 여러 행에 값이 반복돼야 하고, 값이 갈리면 충돌로 따로 빼야 한다.
    version_entries_by_source: dict[int, list[tuple[int, str]]] = {}

    for row_number, hostname, vhost_name, values in raw_rows:
        service_domain = row_map.get((hostname, vhost_name))
        if service_domain is None:
            unmatched_rows.append(
                UnmatchedRow(row_number=row_number, hostname=hostname, vhost_name=vhost_name)
            )
            continue

        if service_name_col is not None and service_name_col < len(values):
            cell_value = values[service_name_col]
            if cell_value not in (None, ""):
                new_value = str(cell_value).strip()
                if new_value != service_domain.service_name:
                    service_name_updates.append(
                        ServiceNameUpdate(
                            row_number=row_number,
                            service_domain_id=service_domain.id,
                            hostname=hostname,
                            vhost_name=vhost_name,
                            old_value=service_domain.service_name,
                            new_value=new_value,
                        )
                    )

        if version_col is not None and version_col < len(values):
            cell_value = values[version_col]
            if cell_value not in (None, ""):
                new_value = str(cell_value).strip()
                version_entries_by_source.setdefault(service_domain.source_id, []).append(
                    (row_number, new_value)
                )

    version_updates: list[VersionUpdate] = []
    version_conflicts: list[VersionConflict] = []
    for source_id, entries in version_entries_by_source.items():
        source = sources_by_id[source_id]
        distinct_values = sorted({value for _, value in entries})
        if len(distinct_values) > 1:
            version_conflicts.append(
                VersionConflict(
                    hostname=source.asset.hostname,
                    row_numbers=[row_number for row_number, _ in entries],
                    values=distinct_values,
                )
            )
            continue

        new_value = distinct_values[0]
        if new_value != source.solution_version:
            version_updates.append(
                VersionUpdate(
                    row_number=entries[0][0],
                    source_id=source_id,
                    hostname=source.asset.hostname,
                    old_value=source.solution_version,
                    new_value=new_value,
                )
            )

    return ServiceImportResult(
        service_name_updates=service_name_updates,
        version_updates=version_updates,
        version_conflicts=version_conflicts,
        unmatched_rows=unmatched_rows,
    )


def apply_service_updates(payload: list[dict]) -> tuple[int, int]:
    """미리보기에서 확정된 항목을 실제로 반영. (반영된 값 개수, 영향받은 자산 수)를 반환."""
    service_name_items = [p for p in payload if p.get("kind") == "service_name"]
    version_items = [p for p in payload if p.get("kind") == "version"]

    changed_asset_ids = set()
    applied = 0

    if service_name_items:
        service_domains = {
            sd.id: sd
            for sd in WebServiceDomain.objects.filter(
                id__in=[item["service_domain_id"] for item in service_name_items]
            ).select_related("source")
        }
        for item in service_name_items:
            service_domain = service_domains.get(item["service_domain_id"])
            if service_domain is None:
                continue
            new_value = item["new_value"]
            if service_domain.source.kind == WebConfigSource.Kind.WEBTOB:
                WebtobVhost.objects.filter(
                    source=service_domain.source, name=service_domain.vhost_name
                ).update(service_name=new_value)
            service_domain.service_name = new_value
            service_domain.save(update_fields=["service_name"])
            changed_asset_ids.add(service_domain.source.asset_id)
            applied += 1

    if version_items:
        sources = {
            source.id: source
            for source in WebConfigSource.objects.filter(
                id__in=[item["source_id"] for item in version_items]
            )
        }
        for item in version_items:
            source = sources.get(item["source_id"])
            if source is None:
                continue
            source.solution_version = item["new_value"]
            source.save(update_fields=["solution_version"])
            changed_asset_ids.add(source.asset_id)
            applied += 1

    return applied, len(changed_asset_ids)
