# CMDB 프로젝트
Django + DRF 기반 CMDB. 자산 자체(신규 생성)는 AWX push 경로 하나뿐이다. 다만 일부 필드 값(수기 입력 동적 필드)은 대시보드에서 사람이 직접 입력할 수 있다 — 아래 "신규 수집 항목 추가" 참고. OS 팩트 외에 웹서버 설정(WebtoB 등) 시각화도 다룬다 — 아래 "웹 서버 설정" 참고. WAS(JEUS 등) 설정도 비슷한 취지로 다룬다 — 아래 "WAS 설정" 참고.

# 환경
- 로컬 개발: Docker Compose + PostgreSQL
- 운영(폐쇄망): Kubernetes + Oracle 19c
- Oracle 호환을 위해 Postgres 전용 SQL/필드(ArrayField, HStoreField 등)는 쓰지 말 것. JSONField는 조회 불가능한 아카이브 용도로만 쓰고, 필터/정렬이 필요한 값은 실제 컬럼이나 동적 필드로 승격할 것.
- **`TextField`는 Oracle에서 NCLOB으로 매핑되고, NCLOB은 `GROUP BY`/`DISTINCT`/`ORDER BY` 대상이 되면 `ORA-00932`로 500 에러가 난다.** Postgres(로컬)는 이 제약이 없어 로컬 테스트로는 절대 못 잡음 — 실제로 폐쇄망 반입 후에만 발견된 사례가 여러 번 있었다(1.0.12, `dashboard/queries.py`). `select_related()`/`annotate()`로 TextField가 있는 모델을 끌어온 쿼리셋에 `.distinct()`나 집계 함수를 쓸 땐 매번 점검할 것: (1) 그 TextField를 `defer()`로 뺐는지, 또는 (2) 애초에 `.distinct()`가 필요한지(검색 필터가 own 필드/forward FK만 참조하면 to-many 조인이 없어 중복 행이 안 생기므로 `.distinct()` 자체가 불필요한 경우가 많음 — 이땐 defer 대신 `.distinct()`를 빼는 게 더 간단하고 안전). 새 목록+검색 화면을 만들 때마다(웹설정/프로세스처럼 TextField를 가진 모델과 얽히는 경우 특히) 확인 대상.

# 수집 구조
- CMDB는 vCenter/Nutanix API를 직접 호출하지 않는다. vCenter/Nutanix는 AWX가 dynamic inventory로 연동해 자동 감지하고, ansible facts 수집 성공 후 하이퍼바이저 메타데이터까지 함께 CMDB로 push한다.
- 새 VM이 아직 ansible로 접속 불가능한 상태라도 CMDB가 즉시 알 필요는 없음 — facts push 시점에만 반영되면 충분.
- 처리 방식은 동기(요청 내 즉시 저장)만 사용. Celery 등 비동기 큐 도입 안 함.

# 신규 수집 항목 추가
- 개발은 외부망, 실행은 폐쇄망 K8s라 새 항목마다 코드 변경→빌드→Harbor push→재배포를 타면 병목이 된다.
- 그래서 자주 안 쓰는/새로 생기는 항목은 고정 컬럼을 추가하지 않고, admin에서 필드 정의(`FactFieldDefinition`)만 등록하면 대시보드 컬럼 노출/정렬/검색까지 코드 수정 없이 되는 동적 필드 구조를 쓴다.
- 동적 필드는 `source`로 두 종류를 구분한다.
  - `AUTO`: raw facts의 한 키를 컬럼으로 승격. AWX push 시 `key`(raw_facts 안의 dot-path)로 자동 추출·저장된다.
  - `MANUAL`: AWX facts에 없는, 사람이 직접 관리해야 하는 값(예: 중요도). raw_facts와 무관하며 대시보드의 자산 행 "편집" 버튼으로 입력·수정한다. push 동기화 대상에서 제외되므로 AWX push가 들어와도 값이 덮어써지지 않는다.
- 두 경우 모두 "필드 하나 = 값 하나"만 다루며, 범용 플러그인/계산식 시스템(다른 필드를 조합한 계산값 등)으로 확장하지 않는다. 단 아래 `os_family_key_overrides`는 여러 필드를 조합해 계산하는 게 아니라 "어느 경로에서 읽을지"만 os_family로 갈리는 좁은 예외라 이 원칙 위반으로 보지 않는다.
- AUTO의 `key`(dot-path)는 `extract_json_path`(`facts/dynamic_fields.py`)가 각 단계마다 dict인지만 확인하고 순회한다 — 경로 중간에 JSON 리스트가 나오면 그 다음부터 무조건 `None`이 된다(인덱싱/필터링 미지원). 예: `ansible_facts.default_ipv4.macaddress`처럼 값이 dict로만 이어지면 등록 가능하지만, `ansible_facts.<interface>.ipv6`처럼 리스트를 거쳐야 하는 값은 지금 구조로는 못 뽑는다.
- **AUTO 필드가 OS(os_family)별로 다른 dot-path에서 값을 가져와야 할 때**(예: OS버전 — 리눅스/AIX는 `distribution_version`이 사람이 읽는 버전이지만 윈도우는 `distribution_version`이 커널 빌드번호라 `distribution`을 대신 써야 함): `FactFieldDefinition.os_family_key_overrides`(JSONField, `{"os_family": "다른 경로"}`)에 **값이 실제로 다른 os_family만** 등록한다. 여기 없는 os_family는 `key`(기본 경로)를 그대로 쓰므로, 대부분의 필드처럼 OS 상관없이 값이 같으면 이 항목을 아예 비워두면 된다(`resolve_field_path`, `facts/dynamic_fields.py`). push 시점(`sync_dynamic_fields`)과 소급 백필(`backfill_field`) 둘 다 호스트의 `HostFact.os_family`를 기준으로 경로를 고른다.
- `source`에는 `FIXED`라는 세 번째 값도 있는데, 이건 "신규 수집 항목 추가"용이 아니라 아래 변경 승인 설정 전용이다 — `HostFact`의 고정 컬럼(os_family/num_cpu 등 8개, `facts.approval.FIXED_FIELD_EXTRACTORS` 참고)을 승인 대상으로 지정할 수 있게 `FactFieldDefinition`에 메타데이터만 얹어둔 것이며 `is_visible=False`로 대시보드 동적 컬럼에는 노출되지 않는다.

# 변경 승인
- 이 승인 절차는 AWX push로 들어오는 값 변경에만 적용된다. 대시보드에서 사람이 직접 입력하는 MANUAL 동적 필드 값은 이 절차를 거치지 않고 저장 즉시 반영된다(이미 사람이 확인하고 넣는 값이라 별도 승인이 불필요하다고 판단).
- 신규 자산(첫 push)은 승인 없이 즉시 반영한다. 이미 존재하는 자산의 값이 바뀌는 경우만 대상.
- 승인이 필요한 필드는 코드 변경 없이 admin의 `FactFieldDefinition` 목록에서 `requires_approval` 체크박스로 지정한다(고정 컬럼/동적 필드 공통, `FactFieldDefinition` 하나로 관리 — 별도 승인 설정 모델 없음). 지정 안 된 필드는 기존과 동일하게 push 즉시 반영.
- push로 들어온 값이 지정 필드의 현재 반영값과 다르면 `PendingChange`로 대기열에 쌓이고, 대시보드(`/dashboard/changes/`)에서 승인해야 실제 반영된다. 반려도 가능. admin에서도 동일한 승인/반려 액션을 제공하지만 일상적인 처리는 대시보드 기준.
- 대시보드 변경 이력 화면에서 여러 건을 체크박스로 골라 한 번에 일괄 승인/반려할 수 있다(운영에서 여러 변경이 한꺼번에 들어오는 상황 대비).
- 대기 중 재push 시: 새 값이 기존 대기 건과 동일하면 무시, 다르면 별도 건으로 쌓는다(덮어쓰지 않음).
- 같은 필드에 여러 건이 대기 중일 때 하나를 승인/반려해도 나머지 대기 건은 자동 정리되지 않는다 — 필요 시 수동으로 함께 정리(대시보드 일괄 처리로 가능).

# 웹 서버 설정
- OS ansible facts와 별개로, 웹서버 설정 파일(WebtoB의 `http.m` 등)을 파싱해 vhost 중심으로 시각화하는 기능. `facts` 앱과는 완전히 분리된 `webconfig` 앱으로 둔다 — ansible facts는 "필드 하나 = 값 하나" EAV 구조인데, 웹서버 설정은 호스트 하나에 vhost/server/uri가 여러 개씩 있고 서로 이름으로 참조하는 관계형 구조라 성격이 다름.
- `WebConfigSource`가 push된 원본 텍스트를 통째로 보관(`raw_content`, 감사/재현용). 종류(`kind`: `webtob`/`apache`/`nginx`)별로 자산당 1개, push마다 구조화 테이블을 전부 지우고 다시 만든다(diff 없이 통짜 교체 — 승인 절차 대상 아님, push 즉시 반영).
- 파서(`webconfig/parsers.py`)와 재생성 로직(`webconfig/sync.py`)은 `kind`별로 분리해서 등록(`PARSERS`/`SYNC_FUNCS` dict). 새 웹서버 종류 추가 시 이 두 군데에 함수 하나씩 등록하면 됨 — WebtoB/Apache/Nginx는 개념 자체가 달라서 억지로 공통 프레임워크로 통일하지 않음.
- WebtoB 구조: `VHost`가 중심 엔티티, `SSL`은 VHost가 이름으로 참조, `SvrGroup`/`Uri`는 `VhostName` 속성으로 VHost를 참조하는데 **콤마로 여러 vhost를 한 번에 지정하는 경우가 있어 ManyToMany**(예: `VhostName = "vhost1,vhost1_ssl"`). `Server`는 `SVGNAME`으로 `SvrGroup`을 참조. 파싱 시점에 이름으로 실제 FK/M2M을 연결해서 저장(문자열 매칭이 아니라 진짜 DB join으로 역추적 가능 — Server→SvrGroup→VHost).
- `VhostName` 없는 `SvrGroup`/`Server`(정적 파일 처리용 공용 그룹 등)는 대시보드 vhost 상세 화면에서는 노출 안 함(vhost 기준 화면이라 자연히 빠짐 — 별도 필터링 코드 불필요, `vhost.svrgroups.all()`로 순회하면 애초에 그 vhost에 안 걸린 svrgroup은 안 나옴).
- `EXT`/`ALIAS`/`LOGGING`/`ERRORDOCUMENT` 등 검색 가치가 낮은 절은 구조화 테이블로 안 만들고 `WebConfigSource.extra_sections`(JSON)에만 보관 — 지금은 원본 설정 펼쳐보기로만 노출, 조회 대상 아님. apache/nginx는 이 개념 자체가 없어(설정 전체가 그냥 vhost 블록의 나열) `extra_sections`를 안 채움 — `raw_content`가 이미 원본 전체를 보존해서 "원본 설정 보기"는 그대로 동작.
- **Apache/Nginx**(`ApacheVhost`/`NginxVhost`): WebtoB와 달리 리버스 프록시 용도뿐이라 SvrGroup/Server/Uri 같은 관계형 모델링을 안 하고 vhost(Apache의 `<VirtualHost>`, Nginx의 `server {}`) 하나 = 행 하나로 끝낸다. ProxyPass/proxy_pass 대상은 관계형 테이블 대신 `proxy_summary`에 콤마로 이어붙인 요약 문자열만 저장(경로 단위로 정확히 봐야 하면 상세 화면의 원본 설정 보기로). `hostname`/`hostalias`/`port`/`service` 필드명을 `WebtobVhost`와 맞춰서 `sync_service_domains()`(`webconfig/sync.py`, kind 공용 duck-typed 유틸)를 수정 없이 재사용한다. `name`(업서트 식별키, 수기 입력한 service를 push마다 보존하기 위함)은 WebToB처럼 설정에 적힌 고유 이름이 없어 `f"{hostname}:{port}"`로 합성.
- **서비스명은 자유 텍스트가 아니라 `core.Service` FK다**(`WebtobVhost`/`ApacheVhost`/`NginxVhost`/`JeusContainer` 공통, 필드명 `service`) — WEB/WAS 양쪽이 문자열이 아니라 같은 Service 행을 참조해야 WebToB↔JEUS처럼 구조적으로 연결된 vhost/컨테이너의 서비스가 오타로 어긋나지 않는다(아래 WAS 섹션의 자동 해석, 그리고 향후 구성도 기능의 전제). 인라인 편집(대시보드 `*ServiceUpdateView`)은 입력한 이름으로 `Service.objects.get_or_create()`해서 연결 — 새 이름을 입력하면 새 Service가 만들어진다(admin `Service`에서 정리 가능). `WebServiceDomain.service_name`(서비스 조회 화면)만 예외적으로 지금처럼 평범한 CharField 비정규화 복사본 유지(도메인 기준 조회에는 문자열이면 충분) - 값 출처만 `vhost.service.name`으로 바뀜.
- 자산 신규 생성은 이 경로로 안 함(자산 생성은 facts push 경로 하나뿐이라는 원칙 유지). WebToB는 hostname을 push payload가 아니라 **설정 내용의 `*NODE` 절 항목 이름**으로 찾지만, apache/nginx 설정 파일에는 서버 자신을 가리키는 절이 없어(ServerName/server_name은 vhost 도메인일 뿐) **AWX가 `inventory_hostname`을 payload의 `hostname` 필드로 별도 전송**하고 그 값을 그대로 쓴다(`webconfig/views.py`의 `_extract_hostname`이 kind로 분기, `awx/push_apache_config_to_cmdb.yml`/`awx/push_nginx_config_to_cmdb.yml`이 `push_facts_to_cmdb.yml`과 같은 `inventory_hostname` 패턴 사용). 어느 kind든 hostname을 못 찾으면 에러(먼저 facts push로 자산이 등록돼 있어야 함).
- 대시보드 `/dashboard/webconfig/`에서 목록(호스트/종류/vhost 수) → 상세(vhost별 카드, 원본 설정은 `<details>`로 접어둠) 확인 — kind 공통 화면이라 webtob/apache/nginx가 한 목록에 섞여 나온다. `vhost_count`는 kind별로 다른 관계(WebtobVhost는 `vhosts`, ApacheVhost는 `apache_vhosts`, NginxVhost는 `nginx_vhosts` related_name)라 세 `Count(distinct=True)`를 더해서 구한다(행 하나는 항상 단일 kind라 최대 하나만 0이 아님). 샘플 데이터는 `samples/webtob/`, `samples/apache/`, `samples/nginx/`.
- **kind별 전용 vhost 목록**(`/dashboard/webconfig/vhosts/`(WebToB), `/dashboard/webconfig/apache/vhosts/`, `/dashboard/webconfig/nginx/vhosts/`, "웹 설정" 드롭다운 하위): 위 `/dashboard/webconfig/` 목록/상세는 서버(자산+kind) 단위 행이라 vhost를 여러 서버에 걸쳐 가로질러 검색·정렬할 화면이 따로 필요해서 신규. **공통 컬럼으로 3종을 한 화면에 합치지 않고 kind별로 화면을 분리 유지**한다 — 공통 뷰가 필요한 자리는 이미 있는 `/dashboard/webconfig/` 쪽이고, 여기는 kind마다 의미 있는 컬럼 구성이 달라서(WebToB는 SvrGroup/Server/URI 요약까지, Apache/Nginx는 Proxy 대상 요약) 억지로 공통 컬럼만 남기면 정보 손실이 큼. WebToB 화면(`WebtobVhostListView`)은 `WebtobVhost` 하나 = 행 하나로, 상세 모달의 vhost 카드에 나오는 값을 전부 컬럼으로 노출한다. `SvrGroup`/`Server`/`URI`는 vhost 하나에 여러 개씩 걸리는 관계형 데이터라 표 한 칸에 못 들어가는데, 모달을 또 띄우는 대신(요청에 따라 "표 안에서 다 끝내기") `build_webtob_vhost_rows()`(`dashboard/queries.py`)가 콤마로 이어붙인 요약 문자열로 만들어 한 칸에 넣는다 — 개별 MinProc/MaxProc까지 정확히 봐야 하면 admin이나 상세 모달로. Apache/Nginx 화면(`ApacheVhostListView`/`NginxVhostListView`)은 관계형 테이블이 없어 `proxy_summary` 필드를 그대로 렌더링하면 되니 별도 요약 빌더가 없다. 서비스명 인라인 편집은 kind별 `*VhostServiceUpdateView`(`/dashboard/webconfig/<kind>/vhost/<pk>/service/`, WebToB만 kind 접두사 없이 `/dashboard/webconfig/vhost/<pk>/service/` — 기존 URL 유지)를 통해 저장하면서 서비스 조회 화면과 값이 동기화된다(내부적으로는 `core.Service`를 `get_or_create`해서 FK로 연결 - API 응답/요청 필드명은 하위 호환을 위해 여전히 `service_name`). 서비스 조회(`WebServiceDomain`)는 kind 공통(도메인/서비스명 중심)으로 계속 좁게 유지하고, SvrGroup/URI/proxy_summary 같은 kind 전용 개념은 각 kind의 vhost 목록/상세 화면에만 둔다. 엑셀 서비스 일괄 반영(`webconfig/excel_import.py`)도 `VHOST_MODELS`(kind → 모델 dict, `PARSERS`/`SYNC_FUNCS`와 같은 패턴)로 세 kind 모두 처리.
- 웹설정 목록의 날짜 컬럼(`최근 변경일`/`최근 반영일`)은 자산 대시보드와 의미를 통일 — 자세한 건 아래 "대시보드" 섹션 참고.
- **웹설정 변경 이력**(`/dashboard/webconfig/changes/`, `WebConfigSourceRevision`): facts의 `PendingChange`와 달리 승인/반려 없는 읽기 전용 감사 로그. `raw_content`가 이전 push와 실제로 다를 때만(동일 재push는 무시) 이전/이후 원본을 한 행에 같이 저장하고(`webconfig/views.py`의 `WebConfigIngestView`에서 갱신 직전에 비교), push 자체는 지금처럼 승인 없이 즉시 반영된다 — 구조(vhost/svrgroup 등 관계형 변화)를 필드 단위로 diff해서 승인 게이트를 거는 방식은 검토 후 기각(웹서버 설정은 "필드 하나=값 하나"가 아니라 관계형이라 PendingChange 구조를 그대로 못 씀, 구조화 테이블만 승인 대기로 묶으면 상세 화면과 원본 보기가 서로 다른 시점을 보여주게 돼서 화면이 헷갈림). 화면에서는 `webconfig/diff.py`의 `unified_diff_lines`로 만든 unified diff를 줄 단위로 색칠(추가=녹색/삭제=빨강, git diff 관례)해서 보여줌.
- **솔루션 버전/Fix는 AUTO**(`WebConfigSource.solution_version`/`solution_fix`, `webconfig/version_extract.py`): 처음엔 수기 입력이었으나(설정 파일 안에 버전 정보가 없어 자동 추출 불가), 세 kind 전부 AWX가 버전 확인 명령 출력을 설정 원본 맨 위에 `# CMDB_SOLUTION_VERSION: <출력>` 마커 주석으로 얹어 보내는 방식으로 통일(WebtoB는 `wsadmin -version`, Apache는 `apachectl -version`, Nginx는 `nginx -v` — 각 플레이북 `awx/push_webtob_config_to_cmdb.yml`/`push_apache_config_to_cmdb.yml`/`push_nginx_config_to_cmdb.yml`). 이 마커는 `#`로 시작하는 줄이라 파서가 그냥 주석으로 버리거나(WebtoB, Apache는 VirtualHost 블록 밖이라 애초에 스캔 대상도 아님) 통째로 잘려나가서(Nginx는 파싱 전 전체 주석 제거) 설정 파싱엔 영향 없음. `VERSION_EXTRACTORS`(kind별 dict, `PARSERS`/`SYNC_FUNCS`와 같은 패턴)가 마커 값을 kind별 형식으로 쪼갠다 — WebToB는 "WebtoB \<버전\> \<나머지 전부\>"로 버전(`5.0`)/Fix(`SP 0 Fix #4 ... 2026/05/19`)를 분리하지만, Apache/Nginx는 애초에 Fix 개념이 없어 `solution_fix`는 항상 빈 문자열이고 버전만 채운다(Apache는 `apachectl -version` 첫 줄 "Server version: ..."에서 접두사만 떼고, Nginx는 "nginx version: ..."에서 동일하게). Apache는 명령 출력이 "Server version"/"Server built" 두 줄인데 두 번째 줄(빌드 날짜)은 안 쓰므로 플레이북이 첫 줄만 마커에 담아 보낸다 — 마커 자체를 한 줄로 만들어 WebToB 때 겪었던 "마커 줄과 다음 내용 사이 개행이 리터럴 `\n`으로 깨지는" 문제를 원천적으로 피함. Nginx는 버전 출력이 stdout이 아니라 stderr로 나가는 게 기본 동작이라 플레이북이 stderr_lines를 우선 확인. 마커가 이번 push에 없으면(아직 role 업데이트 전) 기존 값을 그대로 두고 덮어쓰지 않음 — AUTO라고 무조건 비우면 롤아웃 중간에 값이 사라지는 게 이상해서. AUTO로 바뀌면서 대시보드의 수기 입력 UI(연필 아이콘, 인라인 편집)는 제거함 — 사람이 고쳐도 다음 push 때 조용히 덮어써지므로 읽기 전용으로 노출.

# WAS 설정
- OS ansible facts/웹서버 설정과 별개로, WAS(Web Application Server) 설정 파일을 파싱해 컨테이너 중심으로 시각화하는 기능. `webconfig`와 다른 별도 `was` 앱으로 둔다 — 컨테이너/배포앱 등 개념 집합이 다르고, 아래처럼 "소스=자산 하나" 전제 자체가 달라 억지로 같은 앱에 넣지 않음. 현재는 JEUS 8만 지원(`kind=jeus8`, `samples/jeus8/domain.xml` 기준) — JEUS 6는 파일 구조 자체가 다름(`JEUSMain.xml` + 엔진별 `servlet_engine*/WEBMain.xml`, `samples/jeus6/` 참고)이라 지원하게 되면 별도 kind로 처리.
- **"컨테이너" = domain.xml의 `<server>` 엘리먼트**(예: `adminServer`, `DRNRAP01_CMP1`) — 자기 listen port/JVM/배포앱을 가진 단위로, WebToB의 VHost/Apache의 VirtualHost에 대응(`JeusContainer` 모델, WebtoB의 vhost 필드명·MANUAL `service` 패턴을 그대로 따름).
- **`WasConfigSource.asset`(push를 보낸 admin 서버 호스트) ≠ `JeusContainer.asset`(컨테이너 자신이 속한 호스트) — webconfig 계열과 가장 다른 지점.** domain.xml 하나가 JEUS 도메인 전체(여러 물리 노드에 걸친 컨테이너)를 기술할 수 있는 구조이지만, 실제로 이 파일은 admin 서버가 떠있는 호스트에만 있어서 AWX 수집도 그 호스트에서만 이뤄진다(`awx/push_jeus8_config_to_cmdb.yml` 인벤토리 구성 시 admin 서버 호스트만 대상으로 할 것). 그래서 push 주체(소스)는 admin 호스트 하나지만, 그 안에 담긴 컨테이너들은 각자 다른 `node-name`(=다른 자산)에 속할 수 있어 컨테이너마다 별도로 자산을 조회해 연결한다(`was/sync.py`). 대시보드에서 소스의 hostname과 컨테이너의 hostname을 같은 값으로 가정하면 안 됨 — 특히 `JeusContainerListView`(JEUS8 목록)의 Hostname 컬럼은 반드시 `container.asset`을 쓴다(`source.asset` 아님).
- 소스(admin 호스트) 자산 판별은 WebToB의 `*NODE`절 방식과 동일하게 **content에서 결정적으로 뽑는다** — `admin-server-name`에 해당하는 컨테이너의 `node-name`이 그 값(`was/views.py`의 `_extract_admin_hostname`). apache/nginx처럼 AWX가 별도 hostname 필드를 보낼 필요 없음. 못 찾으면 WebToB와 동일하게 에러.
- **컨테이너 자신의 node-name이 아직 CMDB에 자산으로 등록 안 됐으면 `asset=null`로 그냥 저장**(제외하지 않음) — domain.xml 하나에 여러 노드가 섞여 있어서 하나가 미등록이라고 전체 push를 막으면 이미 등록된 다른 노드의 정상 컨테이너까지 못 들어오게 되므로. 나중에 그 노드가 facts push되면 다음 JEUS push 때 자동으로 연결된다(재동기화 트리거 따로 없음 — 항상 동기 처리 원칙과 동일선상).
- **솔루션 버전은 AUTO지만 마커/명령어 실행이 필요 없다** — domain.xml 루트 엘리먼트의 `version` 속성(예: `version="8.5"`)에 이미 있어서 `was/parsers.py`가 파싱 시점에 바로 뽑는다. WebToB/Apache/Nginx의 `# CMDB_SOLUTION_VERSION:` 마커 방식과 다름.
- **WebToB 연결 교차 참조**(`JeusWebtobConnector`): 컨테이너의 `<webtob-connector>`(JEUS가 WebToB에 등록되는 설정 — `registration-id`, `network-address`)를 `webconfig` 앱의 `WebtobServer`와 실제로 연결해둔다. `registration-id`는 WebToB `*SERVER`(SVRTYPE=JSV)의 이름 자체와 매칭되고, `network-address`는 hostname일 수도 실제 IP일 수도 있어 `Asset.hostname` 매칭을 먼저 시도하고 안 되면 `Asset.primary_ip`로 재시도(`was/sync.py`의 `_resolve_webtob_asset`/`_resolve_webtob_server`). `was` 앱이 `webconfig.models`를 import하는 앱 간 의존이 이 기능 때문에 생김. WebToB 쪽 데이터가 아직 없어 못 찾으면 `webtob_server=null`로 두고 다음 JEUS push 때 재해석 — 컨테이너 자산 미등록과 같은 관대한 원칙.
- **`JeusContainer.service`는 혼합 필드(AUTO-if-resolvable, 아니면 MANUAL)**: webconfig 쪽 vhost.service와 달리 완전 MANUAL이 아니다 — 연결된 `webtob-connector`(들)의 WebtobServer→SvrGroup→vhost(M2M)를 따라가 vhost.service를 모으고, 공백 아닌 값이 **정확히 하나로 겹치면** push 시점에 자동으로 덮어쓴다(`was/sync.py`의 `_resolve_webtob_service`). 이중화(같은 서비스가 WebToB 서버 여러 대에 붙는 흔한 구성)에서 실제 서비스는 보통 같기 때문에 이 방식이 성립. 값이 없거나(연결 자체가 없는 컨테이너, 예: adminServer/배치 컨테이너) 여러 개로 갈리면(서로 다른 서비스가 섞인 이상 케이스) 기존 값을 그대로 두어 대시보드에서 수기 입력한 값이 보존된다. WebToB 쪽 vhost.service를 나중에 고쳐도 실시간 반영은 안 되고 **다음 JEUS push 때 재해석** — `webconfig`↔`was` 앱 간 실시간 동기화(반대 방향 트리거)는 결합도 문제로 만들지 않기로 함, 컨테이너 자산/webtob_server 미확인과 같은 지연 허용 원칙. (대시보드에서 사람이 직접 한쪽을 수정할 때의 즉시 전파는 별도 기능 — 아직 미구현.)
- 대시보드 `/dashboard/was/`(공통 목록, kind 무관) → `/dashboard/was/<pk>/`(상세, 컨테이너별 카드 + WebToB 연결 표시) → `/dashboard/was/jeus8/containers/`(JEUS8 전용 컨테이너 목록, webconfig의 kind별 전용 화면과 동일 취지) → `/dashboard/was/changes/`(변경 이력, webconfig와 동일하게 승인 없는 읽기 전용 diff). 상단 내비게이션 "WEB"과 나란히 "WAS" 드롭다운.

# 시스템
- OS ansible facts/웹서버/WAS 설정과 별개로, vCenter/Nutanix가 보고하는 인벤토리를 별도 `systems` 앱으로 시각화하는 기능. **"시스템" = 진짜 물리 장비(ESXi 호스트/AHV 노드)가 기본 단위**이고, 그 위에 떠있는 OS(VM)는 상세 화면에서 관계형으로 나열한다 — VM을 기본 단위로 두고 물리 호스트를 텍스트 하나로 붙여두는 방식은 기각(물리 장비 자체가 실제 하드웨어 스펙을 갖는 진짜 엔티티여야 한다는 요구). 자산(대시보드 "자산" 개념) ↔ VM ↔ 물리 호스트를 hostname/호스트 참조로 연결해 양방향(시스템 쪽에서 OS 확인, 자산 상세에서 물리 호스트 확인)으로 볼 수 있게 하는 게 목표.
- **호스트 facts push와 완전히 분리된 흐름 — 개별 호스트 단위가 아니라 vCenter 인스턴스/Nutanix Prism Central 하나당 한 번씩 수집한다.** 처음엔 "facts push 시점에 그 호스트가 속한 vCenter/Nutanix를 같이 찔러서 정보를 덧붙이는" 방식을 생각했지만, vCenter가 여러 대 운영되는 실제 환경에서는 호스트 하나가 어느 vCenter에 속하는지 push 시점엔 알 수 없다는 문제가 있어 기각. 대신 AWX가 가진 vCenter/Nutanix를 전부 통째로 조회해 물리 호스트+VM 목록 전체를 CMDB로 배치 push하고, CMDB가 hostname으로 이미 facts push된 기존 자산과 매칭하는 방식을 쓴다(자산 신규 생성은 안 함 — 자산 생성은 facts push 경로 하나뿐이라는 원칙 유지).
- **모델 구조**: `SystemSource`(vCenter 인스턴스 또는 Nutanix Prism Central 하나, `kind`=vcenter/nutanix)는 webconfig/was의 소스와 달리 특정 자산에 연결되지 않는다 — 하나의 소스가 여러 물리 장비를 한 번에 보고하기 때문. `SystemHost`(물리 장비 하나 = 행 하나, "시스템" 탭의 기본 단위)가 `source` FK를 갖고, `SystemVm`(VM=OS 인스턴스 하나 = 행 하나, WebToB의 VHost에 대응)이 `host`(nullable, 소속 물리 장비)와 `asset`(nullable, hostname 매칭) 두 FK를 가지며, `SystemDisk`/`SystemNic`이 `SystemVm`에 1:N으로 딸린다. VM→호스트 매칭은 push payload 안에서 호스트별 `external_id`(vCenter/Nutanix 내부 식별자, moref/ext_id)로 이뤄진다 — VM 쪽이 자기가 속한 호스트의 `external_id`를 `host_external_id`로 실어 보내면 `systems/sync.py`가 그 push 안에서 방금 만든 호스트들과 매칭한다.
- **`SystemHost`는 push마다 지우고 다시 만들지 않고 `(source, external_id)`로 upsert한다 — `SystemVm`만 webconfig/was처럼 통짜 교체(전체 삭제 후 재생성)한다.** 처음엔 호스트도 VM처럼 통짜 교체했는데, `SystemHostFieldDefinition`에 MANUAL 필드를 추가하면서 실제로 push해보니 사람이 입력한 값이 다음 push 때 사라지는 버그가 났다 — 통짜 교체는 매번 새 row를 만드는 거라 그 row에 FK로 매달린 `SystemHostFieldValue`(MANUAL 값 포함)가 같이 날아가버림(facts는 `HostFact`를 아예 안 지우고 `update_or_create`해서 이 문제가 없었던 것). 그래서 호스트만 upsert로 바꾸고, 이번 payload에 없는 호스트(실제로 사라진 물리 장비)만 삭제한다(이 경우는 장비 자체가 없어졌으니 MANUAL 값도 같이 사라지는 게 맞음). `SystemVm`은 MANUAL 개념이 없어서 여전히 통짜 교체가 안전하지만, 정리 기준을 `host` FK가 아니라 `SystemVm.source`(직접 FK, 호스트 매칭 실패 시에도 항상 채워짐)로 잡는다 — `host` FK만으로 CASCADE를 태우면 호스트 매칭에 실패한(host=null) VM은 절대 안 지워지고 계속 쌓이는 버그가 되기 때문.
- **hostname/호스트 매칭은 둘 다 관대한 원칙**(JEUS 컨테이너 자산 미등록, WebToB 커넥터 미해석과 동일) — 하이퍼바이저가 보고하는 VM 이름/게스트 hostname이 실제 OS hostname과 다를 수 있고, 호스트 매칭도 payload 순서/누락에 따라 실패할 수 있어서, 매칭 안 되면 각각 `asset=null`/`host=null`로 저장한다(`SystemVm.hostname`엔 원본 값을 그대로 남겨 화면에서 왜 안 붙었는지 바로 보이게 함). 다음 push 때 재해석.
- **`SystemVm`은 지금도 공식 문서로 확인된 핵심 필드(name/hostname/uuid/power_state/num_cpu/memory_mb/primary_ip/tools_status)를 고정 컬럼으로 두고 나머지(디스크/NIC 세부구조 등)만 `extra`에 보관**한다 — VM 쪽은 이 필드들이 실제로 API 응답에서 바로 나오는 값이라 애매하지 않아서 그대로 유지. `SystemHost`만 아래처럼 정리했다.
- **`SystemHost`의 고정 컬럼은 `name`/`external_id`(+ FK인 `source`, `extra`)뿐이다.** 클러스터/CPU/메모리/모델/전원 상태 같은 스펙은 처음엔 고정 컬럼으로 만들었다가, vCenter/Nutanix 응답 스키마가 버전마다 달라 실측 검증 전이라 값이 거의 항상 비어있는 컬럼이 되는 걸 보고 전부 삭제 — 대신 `SystemHostFieldDefinition`(동적 필드, 아래)으로만 노출하기로 함. 대시보드에 항상 뜨는 고정 값은 **이름/종류(`source.kind`)/VM 수(`vms.count()` 라이브 값)** 셋뿐이다 — `kind`는 `kind_key_overrides`의 분기 기준 자체라 동적 필드가 될 수 없고(facts의 `os_family`와 같은 이유로 고정 유지), `vm_count`는 `extra` 안의 값이 아니라 그 호스트에 연결된 `SystemVm` 수를 그때그때 세는 값이라 애초에 dot-path 추출 대상이 아니다.
- **`SystemHost`도 facts처럼 코드 수정 없이 컬럼을 늘릴 수 있는 동적 필드 구조를 쓴다**(`SystemHostFieldDefinition`/`SystemHostFieldValue`, `SystemHost.extra`의 dot-path를 `key`로 등록) — 위에서 뺀 클러스터/CPU/메모리/모델/전원 상태 등은 전부 이 경로로만 노출한다. `FactFieldDefinition`을 재사용하지 않고 systems 앱 안에 별도로 둔 이유는 그게 `HostFact` 전용으로 짜여 있어 그대로 쓰면 facts↔systems 앱이 다시 결합되기 때문(추출 로직인 `extract_json_path`/`coerce_fact_value`는 `facts/dynamic_fields.py`의 순수 함수를 그대로 재사용). vCenter/Nutanix가 `extra`에 서로 다른 모양으로 원본을 싣기 때문에(vCenter는 `extra.host_summary`, Nutanix는 `extra.host`) `os_family_key_overrides`와 완전히 같은 패턴으로 `kind_key_overrides`(kind별 override, 없으면 `key` 그대로)를 지원한다. 지금은 `SystemHost` 전용이고 `SystemVm.extra`(디스크/NIC 원본 등)엔 아직 없음 — 필요해지면 같은 패턴을 복사해서 추가하면 됨. admin의 "선택한 필드 소급 백필 실행" 액션으로 이미 push된 호스트에도 즉시 소급 반영 가능(facts와 동일, AUTO 필드만 대상). 실제 vCenter/Nutanix 응답을 확인하면 `awx/push_vcenter_systems_instance_tasks.yml`/`push_nutanix_systems_instance_tasks.yml`이 이미 `extra`에 원본 전체를 싣고 있으니, 플레이북은 안 건드리고 admin에서 필드 정의만 등록하면 됨.
- **`SystemHostFieldDefinition`도 facts처럼 `source`(AUTO/MANUAL)를 구분하고 MANUAL은 CHOICE 타입까지 완전히 동일하게 지원한다**(`SystemHostFieldChoice`가 facts의 `FactFieldChoice`에 대응). push 동기화(`sync_host_fields`)는 AUTO만 처리해 MANUAL 값을 절대 덮어쓰지 않는다. 편집 UI도 자산 목록과 동일한 패턴 — "시스템" 목록에서 값이 있는 셀 자체를 클릭(`dash-editable-cell`, MANUAL 값 옆엔 `dash-manual-icon` ✎)하면 전용 모달이 뜨고 `SystemHostManualFieldUpdateView`(`POST /dashboard/systems/<pk>/manual-fields/`)로 저장한다. 물리 호스트 상세 화면(모달로 fetch되는 화면이라 중첩 모달 문제로 인해)은 asset_detail.html과 같은 이유로 읽기 전용 유지 — 편집은 목록에서만.
- AWX 쪽은 `push_vcenter_systems_to_cmdb.yml`/`push_nutanix_systems_to_cmdb.yml`이 `hosts: localhost`로 딱 한 번만 실행되고(관리 대상 서버에 SSH 접속 안 함), 여러 vCenter/Nutanix 인스턴스를 `vcenter_instances`/`nutanix_instances` 리스트로 순회한다(`include_tasks`로 인스턴스별 실제 작업 분리 - 물리 호스트 목록 조회 → VM 목록 조회 → CMDB로 `hosts`/`vms` 두 배열을 함께 push) — 자세한 변수/Credential 구성은 `awx/README.md` 참고.
- 대시보드 `/dashboard/systems/`(물리 장비 목록, kind 공통 — vCenter/Nutanix가 같은 컬럼 구조라 webconfig처럼 kind별 화면을 분리하지 않음) → `/dashboard/systems/<pk>/`(물리 장비 상세). 상단 내비게이션에 "시스템" 단일 링크(변경 이력 없음 — 상태는 계속 바뀌는 게 정상이라 웹설정/WAS처럼 "변경 이력"으로 감사할 개념이 아니라고 판단해 diff/revision 추적 자체를 만들지 않음).
- **시스템 목록도 자산 MANUAL 필드와 동일하게 엑셀 다운로드/업로드를 지원한다**(`systems/excel_import.py`, `dashboard/excel_import.py`와 같은 패턴). 다만 매칭 키가 다르다 — `SystemHost`는 `Asset.hostname` 같은 단일 고유 식별자가 없어서(`external_id`는 유일하지만 vCenter/Nutanix 내부 식별자라 사람이 엑셀에 옮겨 적기엔 부적합) **`source_name`+`name` 복합 키**로 매칭한다(서비스 조회의 `(hostname, vhost)` 복합 키와 같은 이유). 다운로드엔 AUTO+MANUAL 둘 다 참고용으로 싣고 반영 대상은 MANUAL만(AUTO 컬럼을 고쳐 올려도 조용히 무시) — 자산 엑셀 업로드와 완전히 같은 원칙.
  - 같은 이유로 화면(시스템 목록, 자산 상세의 "연결된 시스템" 표)에도 물리 호스트 이름 하나만 보여주지 않고 "소스"(vCenter/Nutanix 인스턴스명) 컬럼을 이름보다 앞(더 넓은 범위가 앞)에 둔다 — OS hostname(예: `DRNRAP01`)은 사이트 운영상 유일하게 관리되지만 `SystemHost.name`(물리 장비명)까지 여러 vCenter/Nutanix 인스턴스에 걸쳐 유일하다는 보장은 없어서, 소스 없이 이름만 보여주면 서로 다른 물리 장비를 같은 것으로 오인할 수 있음.
- **"어떤 OS가 어느 물리 시스템에 떠있나"를 자산관리 관점에서 보는 게 목적이라, 시스템 상세의 VM 표와 자산 상세의 "연결된 시스템" 표는 서로 자기 하드웨어 정보를 보여주지 않고 반대편에 이미 선언된 컬럼을 그대로 재사용한다.** 처음엔 시스템 상세의 VM 표에 `SystemVm` 자신의 필드(전원 상태/vCPU/메모리/IP/디스크/NIC)를 보여주고 자산 상세엔 그 중 일부만 가볍게 보여주는 식으로 만들었는데, VM이 실제로 자산에 매칭된 경우 그 자산의 실제 OS 정보(facts 기준 vCPU/OS버전 등)와 하이퍼바이저가 보고하는 값이 서로 다른 두 관점으로 나란히 보여서 헷갈린다는 지적으로 재설계했다. vCenter/Nutanix가 아는 전원 상태/Tools 상태 같은 부가 정보도 검토했으나, facts가 이미 있다는 것 자체가 수집 시점엔 켜져 있었다는 뜻이라 가치가 낮다고 보고 보류(나중에 필요해지면 재검토).
  - **시스템 상세의 "이 장비에 떠있는 OS(VM)" 표**: 자산 매칭된 VM은 `build_rows()`로 그 자산을 OS 목록과 완전히 같은 컬럼(고정 Hostname/IP/OS + admin 동적 필드 + 최근 변경일/반영일)으로 렌더링(`build_system_host_vm_entries`, `dashboard/queries.py`). 매칭 안 된 VM은 하이퍼바이저가 보고한 hostname만 보여주고 "자산 미매칭"으로 표시 — 애초에 보여줄 OS 정보 자체가 없으므로.
  - **자산 상세의 "연결된 시스템" 표**: 반대로 연결된 `SystemHost`를 시스템 목록과 완전히 같은 컬럼(고정 이름/종류/VM 수 + admin이 등록한 `SystemHostFieldDefinition` 동적 필드)으로 렌더링(`get_system_hosts_for_vms`+`build_system_host_rows` 재사용, 새 컴포넌트 안 만듦).
  - 두 표 다 모달로 fetch되는 화면이라(중첩 모달 회피) 동적 필드는 asset_detail.html과 같은 이유로 읽기 전용 — 편집은 각자의 목록 화면에서만.

# 대시보드
- Django admin과 별개로 검색/정렬/페이지네이션이 되는 조회 화면을 둔다. 신규 자산은 push로 즉시, 승인 대상 필드의 값 변경은 승인 시점에 반영된다.
- 관리는 대시보드 중심으로 가고 Django admin은 최소화한다(주로 `FactFieldDefinition` 필드 정의/승인 대상 지정 같이 자주 안 바뀌는 설정용). 그래서 승인/반려도 admin이 아니라 대시보드의 변경 이력 화면에서 처리한다.
- 대시보드 전체(자산 목록 포함)는 로그인 필요. 계정은 Django 기본 인증(admin과 동일 계정) 그대로 재사용, 별도 권한 체계 새로 만들지 않는다.
- 자산/웹설정 목록 공통으로 **최근 변경일**(실제 값이 바뀐 시점만)/**최근 반영일**(내용 변경 여부와 무관하게 마지막 push 시각, 호스트가 계속 살아있는지 확인용) 두 정렬 컬럼을 둔다 — 용어와 의미를 두 화면에서 통일(`생성일`은 정보 가치가 낮아 뺌). 자산의 `최근 변경일`은 승인된 push 변경 시점뿐 아니라 MANUAL 동적 필드를 대시보드에서 수정한 시점에도 갱신되고, `최근 반영일`은 `HostFact.last_seen_at`. 웹설정의 `최근 변경일`은 `WebConfigSourceRevision`의 최신 감지 시각, `최근 반영일`은 `WebConfigSource.last_pushed_at`.
- 변경 이력(대기/승인/반려 전체)은 `/dashboard/changes/`에서 조회 + 대기 건은 승인/반려 처리까지 가능.
- MANUAL 동적 필드는 자산 목록의 "관리" 컬럼 → "편집" 버튼(모달)으로 값을 입력/수정한다. 변경 이력(`/dashboard/changes/`)에는 남지 않는다 — 승인 대상이 아니기 때문.
- 컬럼이 많은 목록 화면은 앞 두 컬럼이 가로 스크롤 시에도 고정 표시된다(`position: sticky`) — 자세한 건 아래 "대시보드 디자인 패턴" 참고.
- WEB(웹설정/WebToB/Apache/Nginx vhost 목록)·WAS(WAS/JEUS8 컨테이너 목록) 6개 화면 전부 Hostname 바로 오른쪽에 IP 컬럼을 둔다 — 설정 파일 자체엔 IP 정보가 없어서, Hostname과 마찬가지로 이미 연결된 Asset(facts로 등록된 자산)의 `primary_ip`를 그대로 재사용한다(JEUS8만 `source.asset`이 아닌 `container.asset` 기준 — Hostname 컬럼이 참조하는 asset과 항상 동일하게 맞춤).
- 상단 내비게이션은 "자산 대시보드"/"웹 설정"이 각각 드롭다운으로 목록·변경 이력 하위 메뉴를 묶는다(자산=`/dashboard/assets/`+`/dashboard/changes/`, 웹설정=`/dashboard/webconfig/`+`/dashboard/webconfig/changes/`). 변경 이력이 최상단 탭으로 따로 노출되지 않으니, 새 영역에 변경 이력을 추가할 땐 이 드롭다운 패턴을 그대로 따를 것.
- **서비스 조회 엑셀 일괄 업로드**(`webconfig/excel_import.py`): 자산 MANUAL 필드 엑셀 업로드(`dashboard/excel_import.py`)와 같은 흐름(업로드→미리보기→확정)이지만 매칭 키가 다르고 대상 모델도 달라서 별도 모듈로 분리. "엑셀 다운로드"(`/dashboard/services/export/`)로 전체 데이터(검색 필터 무시)를 받아 몇 칸만 고쳐 재업로드하는 걸 기본 흐름으로 삼는다.
  - 매칭 키는 `(hostname, vhost)`다 — **도메인은 매칭 키로 못 씀**(같은 도메인을 http/https vhost 두 개가 나눠 쓰는 실제 케이스가 있어 유일하지 않음, 예: `vhost1`/`vhost1_ssl`이 둘 다 `cal.lotteins.co.kr`). `domain`/`aliases` 컬럼은 사람이 알아보기 위한 참고용으로만 내보내고 업로드 시엔 무시.
  - 서비스명은 vhost 단위 값이라 행 하나 = vhost 하나로 반영. 솔루션버전/Fix는 AUTO 필드로 바뀌면서(위 "솔루션 버전/Fix는 AUTO" 참고) 엑셀로는 수정 불가 — domain/aliases와 같은 참고용 컬럼으로만 내보내고 업로드 시 무시.
  - 기존 값과 실제로 다른 셀만 "반영 예정"에 잡는다(자산 임포터는 이 diff 비교가 없어 안 바뀐 셀도 매번 반영 예정으로 뜨는데, "전체 내보내서 일부만 고쳐 재업로드"하는 흐름에서는 그러면 노이즈가 너무 많아짐).

# 대시보드 디자인 패턴
화면마다 톤이 갈리지 않도록, 새 대시보드 화면/컴포넌트를 만들 때 아래 패턴을 그대로 따른다(Bulma 기반, `dashboard/templates/dashboard/base.html`이 라이트·고대비 테마로 고정).

- **테마는 라이트·고대비 고정**(`data-theme="light"`): 연세 있으신 사용자가 다크 테마를 보기 어렵다는 피드백으로 전환. 다크 배경은 눈부심은 줄지만 나이 들며 낮아지는 대비 감도(백내장 등)엔 오히려 불리해, 순백에 가까운 배경 + 진한 텍스트 조합을 택함. `base.html`의 `:root` 오버라이드로 관리:
  - `--bulma-body-size: 1.125em`으로 전체 기본 글자 크기를 한 단계 키움(브라우저 확대 없이도 읽기 편하게).
  - `--bulma-text-l: 12%`로 본문 텍스트를 기본값(29%)보다 훨씬 짙게, `--bulma-link-l: 42%`로 링크/포인트 색도 흰 배경에서 대비가 나오게 낮춤.
  - 상단 네비게이션(`navbar is-black`)만 예외적으로 어두운 바탕을 유지 — 페이지 본문과 시각적으로 구분되는 앵커 역할(공간 감각 유지 목적, 눈부심과 무관).
  - 표 헤더 밑줄/입력창 테두리는 `border-width: 2px`로 굵게 — 저시력 사용자가 구획을 더 쉽게 구분하도록.
  - 대기/승인/반려 같은 상태 태그는 색만으로 구분하지 않고 `●`/`✓`/`✕` 기호를 같이 붙인다(색각 변화 대비) — 새 상태 태그를 추가할 때도 이 기호 관례를 따를 것.
  - `login.html`은 `base.html`을 extends하지 않는 유일한 화면이라 위 오버라이드를 자체 `<style>`로 따로 갖고 있음 — 테마 값을 바꿀 땐 두 파일 다 같이 수정.
- **제목 계층**: 페이지 최상단 제목은 `title is-4` 하나만 쓴다. 박스/카드 안 하위 섹션 제목(Node, VHost, vhost 이름 등)은 `title is-6`. 로그인처럼 독립된 좁은 폼이나 업로드 결과처럼 페이지 중간의 소제목은 `title is-5`.
- **버튼/태그 색상은 의미로 고정**(임의로 고르지 않음):
  - `is-link`: 주요 제출/저장 액션(검색, 저장, 로그인, 업로드 검증, 확정 등) — 화면당 보통 하나만 강조.
  - `is-success`: 승인/긍정 상태(승인 버튼, "승인" 태그, SSL 활성 태그).
  - `is-warning`: 대기·주의 상태 태그(대기 상태, 값 불일치 경고).
  - `is-danger`: 오류·반려(반려 버튼은 `is-outlined`를 같이 붙여 승인 버튼보다 한 단계 눌러지게, 에러 메시지 `help is-danger`, "반려"/"오류" 태그는 solid).
  - `is-light`: 페이지 이동성 보조 버튼(자산 대시보드의 "엑셀 업로드", 변경 이력의 "대기 건만 보기", 로그아웃).
  - 색상 없는 plain `button`: 취소/중립 액션(모달 "취소" 버튼 등).
- **수기 입력(MANUAL) 값은 옆에 연필 아이콘(✎)을 붙여 구분**(`dash-manual-icon`, base.html에 회색 고정으로 정의). 처음엔 빨간 점으로 구분하려 했으나 빨강은 이미 `is-danger`(오류·반려) 의미로 고정해둔 색이라 오해 소지가 있어 폐기 — 편집 가능 표시는 성공/경고/오류 팔레트와 절대 안 겹치는 중립색만 쓴다. 헤더 색으로 구분하던 이전 방식(자산 대시보드 MANUAL 컬럼 헤더만 다른 색)은 표 형태가 아닌 화면(웹설정 상세의 카드형 라벨-값 줄 등)엔 적용이 안 돼서 버렸고, 값 옆에 붙이는 방식으로 통일 — 표 헤더/표 셀/카드 라벨-값 줄 세 가지 형태 모두 동일하게 적용 가능하고, 빈 값이어도 아이콘은 보이니 그 칸이 편집 가능하다는 게 계속 드러남(터치 기기는 호버가 없어 이 점이 특히 중요).
- **인라인 편집은 "클릭 대상 = 값이 있는 셀 자체"** 원칙(별도 "편집" 버튼 안 씀). 편집 가능한 `<td>`에는 공통 클래스 `dash-editable-cell`(base.html에 `cursor: pointer` 한 줄로 정의)을 붙여서 커서 표시를 화면마다 다시 정의하지 않는다. 저장 UI는 상황에 따라 둘 중 하나:
  - **전용 모달**(자산 대시보드 MANUAL 필드, 서비스 조회 서비스명): 그 화면이 독자적인 최상위 페이지일 때. 값 종류가 text/select/checkbox 등으로 다양하면 이쪽. (서비스 조회의 솔루션버전/Fix는 AUTO로 바뀌어서 이제 편집 UI 없음)
  - **브라우저 `prompt()`**(웹설정 상세의 vhost 서비스명): 이 템플릿이 다른 목록 화면(웹 설정 목록)의 모달에 AJAX로 fetch되어 그대로 삽입되는 경우 한정 — 모달 안에 또 모달을 띄우는 중첩을 피하기 위한 예외.
- **목록 화면 공통 골격**(자산 대시보드/변경 이력/웹 설정 목록/서비스 조회가 전부 동일 구조): `has-addons` 검색 폼 → `table-container` 안 `table is-fullwidth is-hoverable is-striped` → 정렬 가능한 헤더는 `<a href="{% querystring sort=... page=None %}">`로 오름/내림 토글 → 하단 공통 pagination `<nav>` 블록. 새 목록 화면은 이 골격을 그대로 복사해서 시작하면 톤이 저절로 맞는다.
- **컬럼이 많아 가로 스크롤이 생기는 목록 화면**(자산 대시보드, 웹 설정 목록)은 공통 클래스 `dash-scroll-table`(table)/`dash-sticky-col`+`dash-sticky-col-1`/`dash-sticky-col-2`(앞 두 컬럼의 th/td, base.html에 정의)를 써서 셀 줄바꿈 방지 + 앞 두 컬럼 고정을 적용한다. 컬럼이 적어 가로 스크롤이 안 생기는 화면(변경 이력, 서비스 조회 등)엔 안 씀.

# 테스트/검증
- 자동화 테스트 스위트는 사실상 없다(`*/tests.py`는 있지만 비어있음, `manage.py test` 실행해도 0건). 변경 검증은 로컬 Docker Compose에서 curl로 실제 API를 호출하거나 `manage.py shell`로 재현해 직접 확인하는 방식이 관례.
- `samples/facts/`에 실제 AWX facts push 페이로드 샘플을 모아둔다(`README.md`에 재push용 curl 명령 포함). 동적 필드/승인 흐름 등을 검증할 때 새로 지어내지 말고 여기 있는 걸 재사용할 것. 웹서버 설정 샘플은 `samples/webtob/`(호스트네임_http.m 원본 파일), `samples/apache/`(httpd 설정), `samples/nginx/`(nginx.conf) — apache/nginx는 `POST /api/webconfig/`에 `hostname` 필드(기존 자산의 hostname)를 같이 실어야 한다(설정 내용만으로는 자산을 못 찾음, 위 "웹 서버 설정" 참고). WAS 설정 샘플은 `samples/jeus8/domain.xml`(`POST /api/was/`, `kind=jeus8` — hostname 필드는 불필요, admin-server-name에서 자동 판별) — `samples/jeus6/`는 아직 파서가 없어 지금은 못 씀. 시스템(vCenter/Nutanix VM 인벤토리) 샘플은 `samples/systems/`(`POST /api/systems/`) — 매칭 확인을 위해 `samples/facts/`로 이미 등록된 자산과 같은 hostname을 씀.

# 배포
- 이미지는 Harbor로 push 후 K8s Deployment
- NodePort 방식 서비스 노출
- Helm 차트는 `helm/cmdb-core/` (자세한 사용법은 그 안의 README.md). 민감정보(시크릿키/DB 비밀번호/AWX API 키)는 이 리포지토리의 `values.yaml`에 커밋하지 않고 별도 values 파일이나 `existingSecret`으로 주입.
- 마이그레이션은 `manage.py migrate`를 실행하는 Helm hook Job이 install/upgrade마다 자동 처리(별도 워커/큐 없이 동기 처리 원칙과 동일선상).
- 운영 이미지는 `gunicorn`으로 기동, 정적 파일(주로 Django admin CSS/JS)은 `whitenoise`로 이미지 안에서 직접 서빙(별도 nginx/CDN 없음). 로컬 개발은 여전히 `docker-compose.yml`이 `runserver`로 오버라이드.
- Oracle 19c 연결은 `oracledb`(thin mode, Oracle Instant Client 불필요이므로 폐쇄망 vendoring이 단순함)를 사용. `vendor/wheels`에 oracledb/gunicorn/whitenoise 및 의존성(cryptography 등) 포함.

# 이미지 버전 관리
- 버전 기준점은 루트의 `VERSION` 파일 하나뿐이다(예: `1.0.7`). 다른 곳(WORKLOG 등)의 버전 언급은 참고용이지 기준이 아니다 — 항상 `VERSION` 파일을 먼저 확인할 것.
- **앱 코드(런타임에 영향을 주는 파일: `*.py`, 템플릿, 정적 파일, `Dockerfile`, `requirements.txt`, `vendor/`, 마이그레이션 등)가 바뀐 push를 할 때는** 아래를 같이 처리한다 — 이 문서에 미리 승인해둔 절차라 진행 여부 자체를 다시 묻지는 않지만, 5번 커밋 직전에는 "커밋 규칙"대로 항상 확인받는다.
  1. `VERSION`의 patch 버전을 1 올린다(지금까지 patch만 순차 증가시켜온 관례를 따름, 예: `1.0.6` → `1.0.7`).
  2. `docker build -t cmdb-core:<새 버전> .`으로 이미지를 빌드해 문제없이 빌드되는지 확인한다.
  3. `docker save cmdb-core:<새 버전> -o cmdb-core-<새 버전>.tar`로 추출 후 `7z a -tzip cmdb-core-<새 버전>.tar.zip cmdb-core-<새 버전>.tar`로 **zip으로** 압축한다(7z 포맷이 아니라 `.zip`으로 통일 — 압축 도구는 그대로 7-Zip: `C:\Program Files\7-Zip\7z.exe`, PATH에 없으면 이 경로로 직접 호출, `-tzip` 옵션으로 zip 포맷 지정).
  4. `CHANGELOG.md` 맨 위에 새 버전 섹션을 추가해 이번 릴리즈에 포함된 변경사항을 정리한다. `WORKLOG.md`가 개발 과정의 디버깅/검토 기록이라면, `CHANGELOG.md`는 "이 배포 버전에 뭐가 들어갔는지"를 배포자 관점에서 간결하게 정리하는 파일.
  5. **여기서 커밋 전 확인**: `VERSION`/`CHANGELOG.md` 변경사항을 보여주고 승인받은 뒤 커밋 + push한다.
  6. `gh release create v<새 버전> cmdb-core-<새 버전>.tar.zip --title v<새 버전> --notes "<CHANGELOG.md의 해당 버전 섹션 내용>"`으로 GitHub Release를 만들고 압축한 이미지를 첨부한다(`gh`도 PATH에 없으면 `C:\Program Files\GitHub CLI\gh.exe`로 직접 호출). `gh auth login`은 사용자가 미리 해뒀다고 가정 — 로그인 안 돼 있으면 진행 못 하니 사용자에게 알릴 것.
  7. `.tar`/`.tar.zip` 산출물은 리포지토리에 커밋하지 않는다(`.gitignore`에 이미 제외 설정, GitHub Release 첨부파일로만 배포).
  8. Release 업로드까지 끝나면 로컬(스크래치패드 등)에 남은 `.tar`/`.tar.zip` 파일은 지운다 — 원본은 GitHub Release에 있으니 필요하면 거기서 받으면 됨.
  9. 첨부파일 용량이 계속 쌓이는 걸 막기 위해, `gh release list`로 전체 릴리즈를 확인해 **최신 3개를 제외한 나머지 릴리즈는 첨부파일만 삭제**한다(`gh release delete-asset <태그> <에셋파일명> -y`). 태그/릴리즈 노트 자체는 지우지 않음 — 이력 조회는 계속 가능해야 하므로. 실제 이미지가 필요해지면 그 버전을 소스에서 다시 빌드하면 됨.
- `WORKLOG.md`/`CLAUDE.md`처럼 앱 실행에 영향 없는 문서만 바뀐 push는 위 과정을 생략한다.

# 커밋 규칙
- 형식: `<type>: <한글 설명>` (Conventional Commits 기반, 설명만 한글)
- type: `feat`(새 기능), `fix`(버그 수정), `docs`(문서만 변경), `refactor`(동작 변화 없는 구조 개선), `test`(테스트 추가/수정), `chore`(빌드/설정/의존성 등 잡무)
- 예: `feat: 동적 필드 정렬 기능 추가`, `fix: hostname 정규화 누락 수정`
- **`git commit` 실행 전에는 항상 무엇이 바뀌었는지(파일 목록/요약)와 커밋 메시지를 먼저 보여주고 사용자 확인을 받은 뒤 커밋한다.** 세션 종료 절차, 이미지 버전 관리 절차처럼 이 문서에 "자동으로 처리한다"고 적힌 흐름도 예외 없이 이 확인 단계는 거친다 — 빌드/버전업/CHANGELOG 작성 등 커밋 이전 준비 작업까지는 자동으로 진행해도 되지만, 실제 커밋(및 그 이후의 push/release)은 확인 후에 실행.

# 세션 종료
- 사용자가 작업을 종료한다는 취지로 말하면(예: "끝낼게", "여기까지", "작업 종료" 등), 아래를 순서대로 처리한다.
  1. `WORKLOG.md`에 이번 세션 작업 내용을 정리해서 추가(기존 형식 유지, 새 날짜는 위에 추가)
  2. 커밋 규칙에 따라 변경사항(WORKLOG.md 포함) 커밋 — 위 "커밋 규칙"대로 커밋 전 사용자 확인 필수
  3. 확인받으면 원격에 push
- 커밋할 변경사항이 전혀 없으면(WORKLOG.md 갱신도 불필요한 경우) 커밋/push는 건너뛴다.
