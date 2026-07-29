# 릴리즈 노트

이미지 버전(`VERSION`)별로 실제 배포되는 내용 위주로 정리한다. 새 버전은 위에 추가.
개발 과정의 세세한 디버깅/검토 기록은 `WORKLOG.md` 참고.

1.0.6까지의 이력은 이 파일 도입 전이라 별도 기록 없음 — `WORKLOG.md`의 해당 날짜 항목 참고.

## 1.0.15

- Apache/Nginx 웹서버 설정 파싱 추가(WebToB에 이어) — `POST /api/webconfig/`가 `kind: apache`/`kind: nginx`를 받아 `<VirtualHost>`/`server {}` 블록을 vhost 단위로 파싱, 도메인/포트 기준으로 서비스 조회(`WebServiceDomain`)에도 연계. 전용 목록 화면 신규(`/dashboard/webconfig/apache/vhosts/`, `/dashboard/webconfig/nginx/vhosts/`), 서비스명 인라인 편집·엑셀 일괄 반영도 동일하게 지원
- Apache/Nginx 설정 파일에는 서버 자신을 가리키는 절이 없어(WebToB의 `*NODE`와 달리) AWX가 `inventory_hostname`을 payload에 별도로 실어 보내도록 변경 — 신규 플레이북 `awx/push_apache_config_to_cmdb.yml`/`push_nginx_config_to_cmdb.yml` 추가
- Apache/Nginx 솔루션 버전도 AUTO 추출 지원(`apachectl -version`/`nginx -v` 출력을 마커로 첨부). Fix 개념은 WebToB 전용이라 두 kind 모두 항상 빈 값
- 웹설정 목록(`/dashboard/webconfig/`)의 VHost 수 컬럼이 WebToB 기준 하나에만 의존해 Apache/Nginx 소스는 항상 0으로 보이던 것 수정, 검색도 세 kind 모두 대상에 포함
- Oracle `ORA-00932`(NCLOB) 재발 방지: 신규 화면(Apache/Nginx vhost 목록)과 기존 WebToB 설정 목록 둘 다 검색 시 `TextField`(NCLOB) 컬럼이 `.distinct()`에 걸릴 수 있던 걸 발견해 함께 수정(불필요한 `.distinct()` 제거 — 해당 화면들의 검색 필터는 애초에 to-many 조인이 없어 중복 행이 생길 수 없는 구조)

## 1.0.14

- 어플리케이션(프로세스 기반) 동작 여부 조회 화면 신규(`/dashboard/processes/`, 상단 "어플리케이션"). AWX가 각 서버에서 실행한 `ps -ef` 원본을 push하면(`processes` 앱, `POST /api/processes/`), Django admin에 등록해둔 정규식 패턴(`ApplicationDefinition`)에 매칭되는 어플리케이션을 자산별로 보여준다. admin에서 패턴을 새로 등록/수정하면 다음 push를 기다릴 필요 없이 기존에 push된 자산에도 즉시 소급 반영됨
- 대시보드 메뉴 명칭 변경: "자산 대시보드"→"OS"(하위 "자산 목록"→"OS 목록"), "웹 설정"→"WEB"(하위 "웹 설정 목록"→"WEB 목록", "WebToB 설정 목록"→"WEBTOB 목록"), "서비스 조회"→"서비스". 화면 표시 텍스트만 변경(URL/내부 코드명은 유지)

## 1.0.13

- 웹설정 상세 모달의 솔루션 Fix 값이 `...epoll 2026/05/19\n*DOMAIN`처럼 다음 섹션 내용까지 딸려 나오던 문제 수정. AWX가 버전 마커 뒤에 붙이던 개행이 실제 운영 Ansible에서 리터럴 `\n`(백슬래시+n 두 글자)으로 남는 사례가 있었는데, `webconfig/version_extract.py`의 마커 파서가 실제 개행에서만 멈추다 보니 다음 섹션까지 그대로 캡처해버린 게 원인. `version_extract.py`에 리터럴 `\n` 이후를 잘라내는 방어 코드를 추가하고, `awx/push_webconfig_to_cmdb.yml`도 Jinja 문자열 이스케이프 대신 YAML 리터럴 블록의 실제 개행을 쓰도록 변경(keep_trailing_newline 설정에 관계없이 개행이 남도록 빈 줄 하나 추가)해 근본 원인도 같이 손봄
- 기존에 이미 오염된 값이 저장된 자산은 별도 정리 불필요 — AUTO 필드라 다음 AWX push 때 정상 값으로 자동 갱신됨

## 1.0.12

- 웹설정 목록(`/dashboard/webconfig/`)·WebToB 설정 목록(`/dashboard/webconfig/vhosts/`) 조회 시 Oracle에서 `ORA-00932(inconsistent datatypes: got NCLOB)`로 500 에러가 나던 문제 수정. `annotate`/`distinct`에 `raw_content`/`extra_sections`(TextField/JSONField, Oracle에서 NCLOB) 컬럼이 암묵적으로 GROUP BY/DISTINCT 대상에 포함된 게 원인 — 두 쿼리셋 모두 해당 필드를 `defer()`로 제외하도록 수정. 로컬(Postgres)에서는 재현되지 않아 1.0.11 반입 후 운영(Oracle) 반입 시점에 처음 발견됨. 데이터는 영향 없음(문제는 조회 쿼리에만 있었고 AWX push 경로는 별개 코드라 안전) — 이 이미지만 재배포하면 정상화

## 1.0.11

- 솔루션 버전/Fix를 수기 입력에서 AUTO로 전환 — AWX가 `wsadmin -version` 출력을 설정 원본에 마커로 얹어 보내면 CMDB가 자동으로 버전/Fix를 나눠 반영(`webconfig/version_extract.py`), 수기 입력 UI는 제거
- AWX 플레이북 `awx/push_webconfig_to_cmdb.yml` 신규 추가(WebToB 설정 push + 버전 마커 첨부)
- 웹 설정 목록/서비스 조회/변경 이력 화면에 컬럼 클릭 시 오름차순·내림차순 토글 정렬 추가(기존엔 자산 대시보드만 지원)
- 웹설정 상세 모달에 `*NODE`절의 LimitRequestBody, 솔루션 버전/Fix 표시 추가
- WebToB 설정 목록 화면 신규(`/dashboard/webconfig/vhosts/`) — vhost 단위로 여러 서버를 가로질러 검색·정렬(도메인/Port/DocRoot/SSL/SvrGroup/Server/URI 등 모달 상세 정보를 표 하나로)

## 1.0.10

- 웹설정(WebtoB) 화면을 목록에서 모달로 열도록 전환, vhost 목록에서 도메인 검색 지원, vhost별 서비스명 수기 입력, SSL 상세(Protocols/RequiredCiphers) 표시 추가
- 도메인/서비스명 기준으로 가로질러 조회하는 "서비스 조회" 화면 신규(`/dashboard/services/`) — 서비스명·솔루션버전 수기 입력을 웹설정 상세 화면과 동일하게 지원
- 웹설정 변경 이력 신규(`/dashboard/webconfig/changes/`) — 원본 설정이 실제로 바뀐 시점만 감지해 git diff 스타일로 표시(승인 절차 없음, push는 그대로 즉시 반영)
- 자산/웹설정 목록의 날짜 컬럼 용어를 "최근 변경일"/"최근 반영일"로 통일, 자산에도 최근 반영일 신규 노출
- 상단 내비게이션을 "자산 대시보드"/"웹 설정" 드롭다운(목록·변경 이력)으로 재구성
- 다크 테마를 라이트·고대비 테마로 전환(연세 있으신 사용자 가독성 개선) — 기본 글자 크기 확대, 텍스트/테두리 대비 강화, 상태 태그에 기호 병기
- 자산/서비스 조회 양쪽에 엑셀 다운로드 기능 추가(다운로드 → 값만 수정 → 재업로드 흐름), 기존 값과 실제로 다른 셀만 반영 예정으로 잡히도록 업로드 검증 로직 개선

## 1.0.9

- 웹서버 설정(WebtoB `http.m`) 파싱·시각화 기능 신규 추가(`webconfig` 앱). AWX push → VHost 중심으로 SSL/SvrGroup/Server/Uri 관계를 실제 FK/M2M으로 연결해 저장, 대시보드 "웹 설정" 탭에서 조회

## 1.0.8

- gunicorn 워커 클래스를 `sync`에서 `gthread`로 변경(`--worker-class gthread --workers 2 --threads 4`). 유휴 TCP 연결에서 워커가 `sock.recv()`에 블로킹되다 WORKER TIMEOUT으로 SIGKILL당하는 간헐적 현상 완화 목적. 30명 내외 사용자 규모에 맞춘 설정(`Dockerfile`)

## 1.0.7

- 변경 승인 대상 설정을 `ApprovalFieldConfig` 별도 모델에서 `FactFieldDefinition`(`requires_approval` 필드)로 통합. 동적 필드를 승인 대상으로 지정할 때 이중 등록이 필요 없어짐, 관련 admin/승인 로직·마이그레이션 포함
- 대시보드 자산 목록에서 동적 필드 컬럼이 많아지면 셀 텍스트가 줄바꿈되며 행이 세로로 늘어나던 문제 수정 — 이제 컬럼이 늘어나면 줄바꿈 대신 가로 스크롤이 뜬다(`asset_list.html`)
