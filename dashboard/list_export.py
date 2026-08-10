"""목록 화면(엑셀 다운로드가 없던 10개 화면)의 읽기 전용 엑셀 내보내기.

자산 MANUAL 필드(dashboard/excel_import.py)나 서비스 조회(webconfig/excel_import.py)의
엑셀 다운로드/업로드 왕복과 달리, 여기 함수들은 업로드 짝이 없는 단방향 다운로드다 -
컬럼별 필터 UI를 만드는 대신 "엑셀로 받아서 거기서 필터/정렬"하는 용도라 화면에 보이는
검색어/정렬(q/sort)은 무시하고 항상 전체 데이터를 내려준다(자산/서비스 조회의 기존
엑셀 다운로드와 동일 관례). 화면별 get_*_queryset(request)가 이미 검색 필터를 안 걸면
전체 데이터를 반환하므로, GET이 빈 가짜 request로 그 함수들을 그대로 재사용해서 쿼리
로직(및 Oracle NCLOB 관련 주의사항)을 중복시키지 않는다.
"""

from decimal import Decimal
from types import SimpleNamespace

import openpyxl
from django.http import HttpResponse
from django.utils import timezone

from dashboard.queries import (
    build_jeus_container_rows,
    build_webtob_vhost_rows,
    get_apache_vhost_queryset,
    get_change_history_queryset,
    get_jeus_container_queryset,
    get_nginx_vhost_queryset,
    get_process_queryset,
    get_was_config_queryset,
    get_was_history_queryset,
    get_webconfig_history_queryset,
    get_webconfig_queryset,
    get_webtob_vhost_queryset,
)

_NO_FILTER_REQUEST = SimpleNamespace(GET={})


def _cell_value(value):
    """openpyxl이 그대로 못 받는 타입만 변환한다 - tz-aware datetime은 저장 자체가
    거부되고(Excel이 타임존을 지원 안 함), Decimal은 버전에 따라 오류가 나서 float로 뺀다."""
    if value is None:
        return ""
    if isinstance(value, timezone.datetime):
        return timezone.localtime(value).replace(tzinfo=None)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _workbook_response(sheet_title, headers, rows, filename):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    sheet.append(headers)
    for row in rows:
        sheet.append([_cell_value(v) for v in row])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


def export_change_history_workbook() -> HttpResponse:
    changes = get_change_history_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            change.asset.hostname,
            change.field_definition.label,
            change.old_value,
            change.new_value,
            change.get_status_display(),
            change.created_at,
            change.decided_at,
            change.decided_by,
        ]
        for change in changes
    ]
    return _workbook_response(
        "변경 이력",
        ["자산", "필드", "이전 값", "새 값", "상태", "감지시각", "결정시각", "결정자"],
        rows,
        "cmdb_change_history.xlsx",
    )


def export_webconfig_workbook() -> HttpResponse:
    sources = get_webconfig_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            source.asset.hostname,
            source.get_kind_display(),
            source.solution_version,
            source.solution_fix,
            source.vhost_count,
            source.config_path,
            source.last_changed_at,
            source.last_pushed_at,
        ]
        for source in sources
    ]
    return _workbook_response(
        "웹 설정",
        ["Hostname", "종류", "버전", "Fix", "VHost 수", "설정 경로", "최근 변경일", "최근 반영일"],
        rows,
        "cmdb_webconfig.xlsx",
    )


def _history_rows(revisions):
    """WebConfigSourceRevision/WasConfigSourceRevision 공통 - 표에 보이는 건 원본 diff가
    아니라 호스트/종류/감지일 메타뿐이라(원문은 화면에서도 unified diff로 별도 렌더) 엑셀도
    그 메타만 담는다."""
    return [
        [revision.source.asset.hostname, revision.source.get_kind_display(), revision.detected_at]
        for revision in revisions
    ]


def export_webconfig_history_workbook() -> HttpResponse:
    revisions = get_webconfig_history_queryset(_NO_FILTER_REQUEST)
    return _workbook_response(
        "웹 설정 변경 이력",
        ["Hostname", "종류", "감지시각"],
        _history_rows(revisions),
        "cmdb_webconfig_history.xlsx",
    )


def export_webtob_vhost_workbook() -> HttpResponse:
    vhosts = get_webtob_vhost_queryset(_NO_FILTER_REQUEST)
    rows = []
    for row in build_webtob_vhost_rows(vhosts):
        vhost = row["vhost"]
        # *NODE절은 소스당 최대 1개뿐인 OneToOneField 역참조라 없으면 존재 자체가 아니라
        # DoesNotExist를 던진다(hasattr로만 안전하게 확인 가능 - Django가 일부러 그렇게 만듦).
        node = vhost.source.node if hasattr(vhost.source, "node") else None
        rows.append(
            [
                vhost.source.asset.hostname,
                vhost.name,
                vhost.hostname,
                vhost.hostalias,
                vhost.port,
                vhost.docroot,
                node.limit_request_body if node else "",
                "Y" if vhost.ssl_flag else "",
                f"{vhost.ssl.name} ({vhost.ssl.certificate_file})" if vhost.ssl else "",
                vhost.ssl.protocols if vhost.ssl else "",
                vhost.ssl.required_ciphers if vhost.ssl else "",
                vhost.logging,
                vhost.errorlog,
                vhost.service.name if vhost.service_id else "",
                row["svrgroup_summary"],
                row["server_summary"],
                row["uri_summary"],
            ]
        )
    return _workbook_response(
        "WebToB vhost",
        [
            "Hostname", "vhost", "도메인", "HostAlias", "Port", "DocRoot", "LimitRequestBody",
            "SSL", "SSL 인증서", "SSL Protocols", "SSL Ciphers", "Logging", "ErrorLog", "서비스명",
            "SvrGroup", "Server", "URI",
        ],
        rows,
        "cmdb_webtob_vhosts.xlsx",
    )


def export_apache_vhost_workbook() -> HttpResponse:
    vhosts = get_apache_vhost_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            vhost.source.asset.hostname,
            vhost.hostname,
            vhost.hostalias,
            vhost.port,
            "Y" if vhost.ssl_flag else "",
            vhost.ssl_certificate_file,
            vhost.ssl_protocols,
            vhost.ssl_ciphers,
            vhost.docroot,
            vhost.logging,
            vhost.errorlog,
            vhost.proxy_summary,
            vhost.service.name if vhost.service_id else "",
        ]
        for vhost in vhosts
    ]
    return _workbook_response(
        "Apache vhost",
        ["Hostname", "Domain", "ServerAlias", "Port", "SSL", "SSL 인증서", "SSL Protocols", "SSL Ciphers", "DocRoot", "Logging", "ErrorLog", "Proxy 대상", "서비스명"],
        rows,
        "cmdb_apache_vhosts.xlsx",
    )


def export_nginx_vhost_workbook() -> HttpResponse:
    vhosts = get_nginx_vhost_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            vhost.source.asset.hostname,
            vhost.hostname,
            vhost.hostalias,
            vhost.port,
            vhost.listen,
            "Y" if vhost.ssl_flag else "",
            vhost.ssl_certificate_file,
            vhost.ssl_protocols,
            vhost.ssl_ciphers,
            vhost.docroot,
            vhost.logging,
            vhost.errorlog,
            vhost.proxy_summary,
            vhost.service.name if vhost.service_id else "",
        ]
        for vhost in vhosts
    ]
    return _workbook_response(
        "Nginx vhost",
        ["Hostname", "Domain", "Alias", "Port", "Listen", "SSL", "SSL 인증서", "SSL Protocols", "SSL Ciphers", "Root", "AccessLog", "ErrorLog", "Proxy 대상", "서비스명"],
        rows,
        "cmdb_nginx_vhosts.xlsx",
    )


def export_was_config_workbook() -> HttpResponse:
    sources = get_was_config_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            source.asset.hostname,
            source.get_kind_display(),
            source.instance_name,
            source.solution_version,
            source.container_count,
            source.config_path,
            source.last_changed_at,
            source.last_pushed_at,
        ]
        for source in sources
    ]
    return _workbook_response(
        "WAS",
        ["Hostname", "종류", "인스턴스", "버전", "컨테이너 수", "설정 경로", "최근 변경일", "최근 반영일"],
        rows,
        "cmdb_was.xlsx",
    )


def export_was_history_workbook() -> HttpResponse:
    revisions = get_was_history_queryset(_NO_FILTER_REQUEST)
    return _workbook_response(
        "WAS 변경 이력",
        ["Hostname", "종류", "감지시각"],
        _history_rows(revisions),
        "cmdb_was_history.xlsx",
    )


def export_jeus_container_workbook() -> HttpResponse:
    containers = get_jeus_container_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            row["container"].asset.hostname if row["container"].asset else "(미등록)",
            row["container"].source.instance_name,
            row["container"].name,
            row["container"].node_name,
            row["container"].listen_port,
            row["container"].ssl_port,
            row["container"].deployed_apps_summary,
            row["webtob_connector_summary"],
            row["container"].service.name if row["container"].service_id else "",
        ]
        for row in build_jeus_container_rows(containers)
    ]
    return _workbook_response(
        "JEUS 컨테이너",
        ["Hostname", "인스턴스", "컨테이너", "Node", "Listen Port", "SSL Port", "배포된 앱", "WebToB 연결", "서비스명"],
        rows,
        "cmdb_jeus_containers.xlsx",
    )


def export_process_workbook() -> HttpResponse:
    snapshots = get_process_queryset(_NO_FILTER_REQUEST)
    rows = [
        [
            snapshot.asset.hostname,
            ", ".join(d.definition.name for d in snapshot.detected_applications.all()),
            snapshot.collected_at,
        ]
        for snapshot in snapshots
    ]
    return _workbook_response(
        "어플리케이션",
        ["Hostname", "감지된 어플리케이션", "최근 반영일"],
        rows,
        "cmdb_processes.xlsx",
    )
