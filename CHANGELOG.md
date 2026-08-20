# 릴리즈 노트

이미지 버전(`VERSION`)별로 실제 배포되는 내용 위주로 정리한다. 새 버전은 위에 추가.
개발 과정의 세세한 디버깅/검토 기록은 `WORKLOG.md` 참고.

1.0.6까지의 이력은 이 파일 도입 전이라 별도 기록 없음 — `WORKLOG.md`의 해당 날짜 항목 참고.

## 1.0.47

- **서비스 관련 리소스 목록 신규** — 서비스 구성도(`/dashboard/services/topology/`)가 지금까지 그래프만 보여줬는데, 그 아래에 같은 데이터를 표(WEB/WAS/DB, 각 행에 OS·시스템 컬럼 포함)로 펼쳐 검색/복사하기 쉽게 했다. `dashboard/topology.py`의 그래프 생성 로직을 `collect_service_resources()`(쿼리 수집)와 `build_service_topology_graph()`/`build_service_resource_table()`(그래프/표 각각 생성)로 분리해 같은 소스 데이터를 그림과 표가 항상 일치하게 공유한다.
- **OS/시스템/DB에 "서비스" 라벨 노출(계산형) + 수기 보정** — 지금까지 서비스는 WEB vhost/WAS 컨테이너에만 보였는데, 그 자산에 연결된 vhost/컨테이너의 service를 역추적해 자산/시스템/DB 목록·상세에도 "이 자원이 어느 서비스에 영향받는지" 보여준다(`dashboard/queries.py`의 `get_service_labels_for_*` 함수들, 계산값이라 저장 없이 매번 조회). DB는 이전까지 서비스 가시성이 전혀 없던 빈틈이었는데 `JeusDataSource.db_instance` 역추적으로 새로 채웠다. 자동 계산이 못 찾는 경우(WEB/WAS가 아예 없는 DB 전용 서버, SID 불일치 등)를 메꾸도록 `Asset`/`SystemHost`/`DbConfigSource`에 `manual_services`(M2M, 계산값과 합집합) 필드를 추가하고 목록 화면에 ✎ 아이콘으로 추가/해제 모달을 붙였다(기존 서비스만 선택 가능, 오타로 새 서비스가 생기지 않음). 모든 서비스 라벨/서비스명은 이제 구성도로 바로 넘어가는 링크라 "이 자원을 건드리면 어떤 서비스가 영향받는지 → 그 서비스에 뭐가 다 물려있는지"를 한 번에 확인할 수 있다.
- **네트워크 탭 다중 홉(hop) 지원** — 지금까지 서비스당 VIP/실서버 매핑을 하나만 등록할 수 있었는데, WEB(Apache/Nginx)→GW→WAS처럼 같은 서비스 안에서 VIP를 여러 번 거치는 실제 구성을 표현할 수 없다는 한계가 있었다. `ServiceNetworkMapping.service`를 `OneToOneField`에서 `ForeignKey`로 바꾸고 `hop_order`(체인 순서, 등록 순서로 자동 배정)/`label`(구간명, 자유 텍스트) 필드를 추가해 서비스당 여러 홉을 등록·편집·삭제할 수 있게 했다. 구성도 그래프도 hop_order 순으로 VIP 노드를 점선 체인으로 잇는다(마지막 홉의 실서버만 기존 WAS 컨테이너와 asset 매칭). 이 과정에서 실서버 asset이 WAS 컨테이너로 안 잡혀도(예: Apache가 도메인을 받아 Tomcat에 VIP로 넘기는 구성) OS 박스만이라도 그려서 체인이 끊기지 않도록 수정 — Tomcat 지원 전에는 이런 경우 그래프에서 뒷단이 통째로 사라지던 버그였다.
- **Tomcat WAS 지원 신규(`kind=tomcat`)** — JEUS와 완전히 다른 제품이지만 `JeusContainer`/`JeusDataSource` 모델과 `sync_jeus` 동기화 로직을 코드 수정 없이 그대로 재사용(`was/parsers.py`의 `parse_tomcat`이 같은 반환 형태만 맞춰줌). `server.xml`의 `<Service>`→컨테이너, `<Connector SSLEnabled>`→listen/ssl port, `<Engine><Host><Context>`→배포앱 요약, `context.xml`의 `<Resource type="javax.sql.DataSource">`→데이터소스(Oracle JDBC URL을 정규식으로 파싱)로 매핑한다. server.xml엔 자기 자신을 가리키는 hostname 정보가 없어 Apache/Nginx와 동일하게 AWX가 `hostname` 필드를 별도로 실어 보내야 한다(`awx/push_tomcat_config_to_cmdb.yml` 신규). **JEUS 목록과는 완전히 분리된 별도 "Tomcat 목록"(`/dashboard/was/tomcat/containers/`) 화면으로 제공** — Tomcat 설정엔 WebToB 연결 개념이 없어 JEUS 목록의 "Node"/"WebToB 연결" 컬럼 대신 데이터소스 목록을 보여준다(kind 무관 종합 조회는 기존 "WAS 목록" 그대로). IP는 Apache/Nginx와 동일한 기존 원칙대로 별도로 안 받고 hostname으로 찾은 기존 자산의 `primary_ip`를 그대로 재사용.

## 1.0.46

- **서비스 네트워크(VIP/실서버) 매핑 신규 기능** — 운영계 이중화 구성에서 Apache/Nginx는 WebToB↔JEUS 커넥터와 달리 뒷단을 VIP/도메인 하나로만 지정해 설정 파일 내용만으로는 실서버가 몇 대인지 알 수 없다는 한계가 있어, 사람이 직접 등록하는 신규 `network` 앱(`ServiceNetworkMapping`/`ServiceNetworkBackend`)을 추가했다. 최상위 "네트워크" 탭(시스템↔서비스 사이)에서 서비스별 외부 도메인/공인 IP/내부 VIP/실서버 목록을 편집하며, 실서버는 hostname 우선·IP 재시도로 기존 자산에 자동 매칭된다. 서비스 구성도(`/dashboard/services/topology/`)에도 연동해 VIP를 마름모 노드로, 여기서 나가는 연결은 WebToB↔JEUS의 확인된 연결(실선)과 구분되게 점선으로 그린다.
- **fix: JEUS↔WebToB 커넥터 자산 매칭 시 500 에러 잠재 버그 수정** — `was/sync.py`의 `_resolve_webtob_asset`이 `network-address`가 등록 안 된 hostname이면서 IP 형식도 아닌 경우 `Asset.primary_ip` 조회에서 바로 `ValueError`를 내며 JEUS push 전체가 실패할 수 있던 문제. 위 네트워크 매핑 기능을 구현하며 같은 패턴의 코드를 새로 작성하다 발견해 함께 수정.
- **서비스(`core.Service`) 명시적 생성 정책으로 전환** — 지금까지 WEB/WAS 배정 화면이나 서비스 엑셀 업로드에서 새 이름을 입력하면 `get_or_create`로 조용히 새 Service가 생성됐는데, 서비스에 네트워크 매핑처럼 실제 데이터가 붙기 시작하면서 오타 하나가 기존 서비스와 어긋난 새 서비스를 만들어버리는 위험이 커져 정책을 바꿨다. 이제 배정 화면/엑셀 업로드 모두 기존에 등록된 서비스명만 선택 가능하고(입력창은 `<input list>` datalist로 오타 방지 보조), 새 서비스는 반드시 먼저 명시적으로 생성해야 한다.
- **"서비스" 메뉴를 "서비스 관리"/"서비스 배정" 두 화면으로 분리** — "서비스 관리"(`/dashboard/services/manage/`)에서 Service 자체를 생성/이름변경/삭제하고(삭제 전 배정 건수 확인 가능, WEB/WAS FK는 SET_NULL이라 안전), "서비스 배정"(기존 `/dashboard/services/`)에서 WEB vhost/WAS 컨테이너에 서비스를 배정한다. 향후 서비스 그룹 등 Service에 속성이 늘어날 것을 염두에 둔 구조 변경.

## 1.0.45

- **서비스 구성도 Oracle NCLOB 오류(ORA-00932) 긴급 수정** — 1.0.43에서 추가한 DB 노드를 내부망(Oracle)에서 실제로 열어보니 `/dashboard/services/topology/`가 500 에러(`django.db.utils.DatabaseError: ORA-00932: inconsistent datatypes: expected - got NCLOB`). `dashboard/topology.py`의 `JeusDataSource` 조회가 M2M(`containers__id__in`) 조인 때문에 `.distinct()`가 필요한데, 같이 쓴 `select_related("db_instance__source", ...)`가 `DbInstance.extra`/`DbConfigSource.raw_content`/`DbConfigSource.extra`(전부 Oracle에서 NCLOB으로 매핑)까지 SELECT 목록에 끌고 들어와 DISTINCT 대상에 NCLOB이 섞인 게 원인. `.distinct()`는 실제로 필요한 조인이라 빼는 대신, 이 화면에서 안 쓰는 세 필드를 `.defer()`로 SELECT에서 제외해 수정(`dashboard/queries.py`의 기존 DB 인스턴스 목록 쿼리와 동일한 패턴). 로컬 Postgres에서는 이 제약이 없어 재현이 안 되던 사례 — CLAUDE.md에 이미 경고돼 있던 패턴이 실제로 반입 후에야 발견됨.

## 1.0.44

- **DB 상세 모달 정리 + 동적 필드 노출 누락 수정** — DB 상세(`/dashboard/database/<pk>/`) 상단 요약 문단에 텍스트로 몰려있던 Role/Open Mode/Log Mode/Characterset/Platform 값을 인스턴스 카드와 동일한 표(label-value) 형태로 옮겨 가독성을 개선했다. 이 과정에서 `Db config source field definition`에 등록한 동적 필드(AUTO/MANUAL)가 목록 화면(`/dashboard/database/`)에는 컬럼으로 나오는데 상세 모달에는 아예 안 나타나던 문제를 발견 — `SystemDetailView`가 이미 쓰고 있던 패턴(`build_db_config_rows()`로 만든 row를 컨텍스트에 담아 상세 템플릿에서 `row.dynamic_cells`로 렌더링)을 `DbConfigDetailView`에도 동일하게 적용해 수정했다. 이제 OS(자산)/시스템/DB 세 상세 화면 전부 admin에서 필드를 추가하면 코드 수정 없이 목록·상세 양쪽에 반영된다(OS/시스템은 원래부터 정상 동작하고 있었음을 재확인).
  - 단순 pk 단건 조회(`select_related`/`prefetch_related`만 추가, `.distinct()`/`annotate()`/`order_by()` 없음)라 Oracle NCLOB(`ORA-00932`) 위험과는 무관함을 모델 필드(TextField/JSONField 위치) 확인으로 별도 점검.
  - 테스트 필드를 임시로 등록해 자산/시스템/DB 세 상세 화면에 실제로 값이 반영되는 것까지 확인 후 정리.

## 1.0.43

- **서비스 구성도에 DB 노드 추가** — `/dashboard/services/topology/`가 지금까지 WEB↔WAS만 그렸는데, 이미 그래프에 있는 WAS 컨테이너가 참조하는 `JeusDataSource` 중 `db_instance`가 매칭된 것을 따라가 DB 노드/엣지까지 그린다(`dashboard/topology.py`). DB는 서비스에 직접 배정되는 대상이 아니라(서비스는 vhost/컨테이너에만 배정) 이미 그래프에 있는 WAS 컨테이너의 실제 연결을 따라 간접적으로만 편입 — WebToB<->JEUS 엣지와 같은 원칙(서비스 배정이 아니라 실제 연결을 따라감). 같은 DB 인스턴스를 여러 컨테이너가 공유하면 노드는 하나만 만들고 엣지만 컨테이너 수만큼 추가. 실제 서비스(CMP Web Service)로 WEB→WAS→DB 3단 연결이 SVG에 정상 렌더링되는 것까지 확인.
- **DB(Oracle)/WAS↔DB 교차 연결 내부망 실측 검증 완료 기록** — 1.0.42 반입 후 실제 push로 확인한 결과를 CLAUDE.md에 반영(코드 변경 없음): `listener_port`(1523) 등 인스턴스 메타정보 전부 정상 수집, `JeusDataSource.database_name`(SID) 기준 WAS↔DB 매칭도 실제로 성공(단, 매칭은 WAS push 시점 기준이라 DB push 이후 WAS를 재push해야 반영됨).
- **상세 모달 간 진짜 중첩 드릴다운(자산↔시스템, WAS→WEB/DB) 추가 + "연결된 DB" 중복 표시 수정** — 자산 상세의 "연결된 시스템", 시스템 상세의 "이 장비에 떠있는 OS", WAS 상세의 "연결된 WebToB"/"연결된 DB"가 지금까지 전체 페이지 이동이었는데, 목록 화면에서 이미 열려있는 모달 위에 진짜로 새 모달(`crossDetailModal`)을 쌓아 클릭한 대상의 상세를 보여주도록 변경 — 통합대시보드 도넛의 목록 모달(iframe)과 같은 "모달 위에 모달" 결과를, 여기선 대상이 검색/정렬 없는 단순 상세라 iframe 없이 별도 `.modal` 엘리먼트(z-index 명시)만으로 구현. 첫 모달은 항상 고정된 복귀 지점이고 위 모달만 닫으면 자동으로 첫 모달로 돌아가 별도 "뒤로가기" 버튼이 필요 없음(교차 모달 안에서 또 링크를 클릭하면 세 번째 모달을 쌓지 않고 같은 교차 모달 내용만 갈아끼워 무한 중첩 방지). Playwright로 두 모달이 동시에 active인 것, 아래 모달 내용이 안 바뀐 채 유지되는 것, 위 모달을 닫으면 아래 모달이 그대로 남는 것까지 실제 클릭으로 검증. WAS의 "연결된 DB"는 `db_unique_name`/`instance_name`을 둘 다 보여줘서 중복돼 보이던 걸 `db_unique_name` 하나만 보여주도록 정리.

## 1.0.42

- **DB(Oracle) push 400 오류 긴급 수정** — 실사용 환경(내부망 AWX)에서 1.0.41의 DB 수집 기능을 실제로 돌려보니 `CMDB로 DB 정보 push` 태스크가 `{"content": ["유효한 문자열이 아닙니다."]}`로 매번 400 실패. 원인은 sqlplus 출력이 `NULL`/`true`/`false` 없이 문자열·숫자만으로 구성된 순수 JSON 텍스트일 때, Ansible이 `"{{ 표현식 }}"` 단독 템플릿의 결과를 문자열이 아니라 Python 리터럴(dict)로 오인 변환(native jinja 타입 추론)해서 `content`가 문자열이 아니라 객체로 전송된 것 — WebToB/JEUS 등 기존 플레이북은 원본이 XML/설정 텍스트라 이 문제를 피해갔는데 Oracle만 출력이 순수 JSON이라 처음 걸린 케이스.
  - `awx/push_oracle_config_to_cmdb.yml`: `content` 렌더링에 `| string` 필터를 마지막으로 추가해 근본 수정(항상 리터럴 문자열로 전송).
  - `database/serializers.py`/`database/views.py`: 다른 ansible-core 버전/설정에서 같은 문제가 재발해도 안전하도록 `content` 필드를 `CharField`가 아니라 `JSONField`로 받아 문자열/dict 둘 다 허용하고, 문자열이 아니면 `json.dumps`로 재직렬화하는 방어 로직 추가(정상 케이스 동작은 그대로).
  - 부수 수정: `DbInstance.startup_time`/`DbConfigSource.db_created_at` 파싱 시 naive datetime(타임존 정보 없는 sqlplus `TO_CHAR` 출력)을 Django 기본 타임존으로 aware 처리하도록 수정 — 매 push마다 나던 `RuntimeWarning` 제거.
  - 버그 재현(문자열 대신 dict를 보내는 페이로드) + 회귀 테스트(정상 문자열 페이로드)로 양쪽 다 200대 응답 확인 후 검증용 데이터 정리.

## 1.0.41

- **DB(Oracle 12c/19c) 정보 수집 신규 지원** — OS ansible facts/웹설정/WAS/시스템과 별개로 DB 인스턴스 정보를 시각화하는 새 `database` 앱. CMDB가 DB에 직접 접속하지 않고 vCenter/Nutanix와 동일 원칙으로 AWX가 DB 호스트에서 로컬 `sqlplus`(오라클 OS 계정 인증 — DB 비밀번호 저장 불필요)를 실행해 결과(JSON)를 push한다.
  - Oracle 12c/19c 둘 다 지원하는 `JSON_OBJECT`/`JSON_ARRAYAGG` SQL 함수로 DB 자신이 CMDB가 기대하는 JSON을 직접 만들어 출력 — WebToB/Apache처럼 텍스트를 정규식으로 파싱하는 대신 `json.loads`만 하면 됨(`awx/push_oracle_config_to_cmdb.yml`, `database/parsers.py`).
  - RAC(멀티노드) 지원 — 대표 노드 1대에서 `GV$INSTANCE` 조회만으로 클러스터 전체 인스턴스가 나오는 걸 이용(WAS의 domain.xml과 동일 원리). `DbConfigSource`(DB 하나, 매칭 키는 `asset`이 아니라 Oracle이 보장하는 전역 유일값 `db_unique_name`)와 `DbInstance`(인스턴스=SID 하나, RAC는 노드 수만큼) 2단 모델.
  - **소스 변경 없이 컬럼 추가 가능** — `SystemHostFieldDefinition`과 동일한 동적 필드 구조(`DbConfigSourceFieldDefinition`/`DbConfigSourceFieldValue`, AUTO/MANUAL + CHOICE 지원)를 갖춰, push된 JSON 원본(`DbConfigSource.extra`)에서 admin이 `key`/`label`만 등록하면 코드 수정·재배포 없이 대시보드 컬럼/엑셀 다운로드에 새 값이 나타난다. 이미 push된 DB에도 "선택한 필드 소급 백필 실행"으로 즉시 반영 가능.
  - 대시보드 `/dashboard/database/`(DB 목록) → `/dashboard/database/<pk>/`(상세, 인스턴스별 카드) → `/dashboard/database/instances/`(인스턴스 전용 목록) → `/dashboard/database/changes/`(변경 이력, 승인 없는 읽기 전용 diff). 상단 내비게이션에 WAS와 나란히 "DB" 드롭다운. 세 목록 화면 전부 엑셀 다운로드 지원(DB 목록은 MANUAL 필드 업로드 왕복까지).
  - **WAS↔DB 교차 참조 추가**: `JeusWebtobConnector`(WAS↔WebToB)와 같은 취지로 `JeusDataSource.db_instance` FK 신규 — JEUS의 데이터소스 설정(`database-name`, 실제로는 Oracle SID)을 `DbInstance.instance_name`과 매칭해 WAS 상세 화면에서 "이 컨테이너가 실제로 어느 DB에 붙는지" 바로 보여준다. RAC에서 흔한 VIP/SCAN 접속 주소는 `DbInstance.host_name`(실제 OS hostname)과 다를 수 있어 host는 매칭에 안 쓰고 SID 이름만으로 매칭(`was/sync.py`의 `_resolve_db_instance`) — 실제 domain.xml 샘플로 검증(Oracle 데이터소스 1건 정상 매칭, MariaDB 등 비Oracle 데이터소스는 매칭 대상 없어 정상적으로 미확인 처리됨).
  - **주의**: 이 저장소 개발 환경에 실제 Oracle 인스턴스가 없어 AWX 플레이북의 SQL(특히 `listener_port` 정규식 추출)은 아직 실측 검증되지 않았다 — 반입 후 실제 sqlplus 출력으로 확인 필요(`samples/oracle/README.md` 참고). CMDB 쪽(파싱/저장/대시보드/엑셀/WAS 교차 연결)은 합성 payload(Standalone 19c + RAC 12c 2노드)와 실제 JEUS8 샘플(`samples/jeus8/domain.xml`)로 전부 검증 완료.

## 1.0.40

- **엑셀 다운로드 13개 화면 전수 검증 후 화면 컬럼 누락/순서 불일치 수정** — "화면에 보이는 정보가 엑셀에도 다 담기는지" 검증 요청으로 13개 다운로드 엔드포인트를 전부 실제 호출해 대조한 결과, 데이터(행)는 필터 없이 전량 내려오지만 컬럼 일부가 화면과 다른 8곳을 발견해 수정.
  - 웹설정/WebToB/Apache/Nginx vhost·WAS/JEUS 컨테이너 6개 목록(`dashboard/list_export.py`): 화면엔 Hostname 바로 옆에 있는 **IP 컬럼**이 엑셀엔 전부 빠져 있어 추가.
  - 자산(OS) 목록(`dashboard/excel_import.py`): 화면 마지막 두 컬럼인 **최근 변경일/최근 반영일**이 엑셀엔 없어 추가(다운로드 그대로 재업로드해도 참고용 컬럼으로 무시되도록 헤더 등록).
  - 시스템 목록(`systems/excel_import.py`): 화면의 **VM 수** 컬럼이 엑셀엔 없어 추가 — `dashboard/queries.py`의 기존 패턴과 동일하게 `.defer("extra", "source__raw_response")` 후 `annotate(Count("vms", distinct=True))`로 계산(Oracle NCLOB이 GROUP BY에 걸리는 문제 방지).
  - 서비스 탭(`webconfig/excel_import.py`): 엑셀 컬럼 순서(hostname/vhost가 항상 맨 앞)가 화면 순서(서비스명→도메인→포트→Hostname→솔루션)와 달라 헷갈린다는 지적으로 화면 순서에 맞춰 재배치, 화면엔 있는데 엑셀엔 없던 **포트/솔루션(종류)** 컬럼도 함께 추가. 매칭 키(hostname/vhost)가 더 이상 고정 0/1번 컬럼이 아니게 되어, 헤더를 위치가 아니라 이름으로 찾도록 `parse_service_workbook`을 리팩터링(향후 컬럼 순서를 또 바꿔도 매칭이 깨지지 않음).
  - 13개 엔드포인트 재검증(200 OK, 엑셀 행 수=쿼리셋 count 일치) + 자산/시스템/서비스 3종 "다운로드 → 그대로 재업로드" 라운드트립(반영 0건/불일치 0건)까지 확인.

## 1.0.39

- **통합대시보드 도넛 드릴다운에서 버전 조각 클릭 시 실제 목록을 모달로 표시** — 종류(OS Family/WEB kind/WAS kind) 타일 클릭으로 펼쳐지는 버전별 도넛에서, 파이 조각이나 범례 행을 클릭하면 그 버전에 해당하는 항목 목록이 모달로 뜬다. 새 테이블/뷰를 만드는 대신 기존 조회 화면(`/dashboard/assets/`, `/dashboard/webconfig/`, `/dashboard/was/`)을 그대로 재사용 — `get_asset_queryset()`/`get_webconfig_queryset()`/`get_was_config_queryset()`(`dashboard/queries.py`)에 정확 일치 필터(`os_family`/`os_version`, `kind`/`solution_version`, "버전 미상" 포함)를 추가하고, 그 화면을 필터+`embed=1` 쿼리스트링을 붙여 iframe으로 모달에 그대로 불러온다. 검색/정렬/페이지네이션/행 클릭 상세 모달까지 그 화면의 기능이 전부 그대로 동작. `embed=1`이면 상단 내비게이션/제목/버튼/검색창을 감추고 표+페이지네이션만 보이게 하고(`base.html`/세 목록 템플릿), 필터 없이 그 화면에 직접 들어오면 "필터 적용됨" 배너+해제 링크를 보여준다. Django 기본 클릭재킹 방지(`X-Frame-Options: DENY`)가 자기 자신을 iframe에 넣는 것도 막아서 `X_FRAME_OPTIONS = "SAMEORIGIN"`으로 완화(같은 origin 내장만 허용, 실제 클릭재킹 방지는 유지).

## 1.0.38

- **자산 목록 검색 Oracle 500 에러 긴급 수정** — `/dashboard/assets/` 검색창(`q`)을 쓰면 Oracle에서 `ORA-00932(NCLOB)`로 항상 실패하던 버그. `get_asset_queryset()`(`dashboard/queries.py`)이 검색 시 `.distinct()`를 거는데 `select_related("hostfact")`가 `HostFact.raw_facts`(JSONField→Oracle NCLOB)를 SELECT 목록에 그대로 끌고 들어온 게 원인 — 1.0.12에서 웹설정 쪽에 이미 적용된 defer 패턴이 정작 자산 목록 자체에는 빠져 있었음. `.defer("hostfact__raw_facts")` 추가로 수정, 실제 쿼리(`str(qs.query)`)로 SELECT 목록에서 `raw_facts`가 빠진 것까지 확인. 상세 화면은 별도 쿼리라 영향 없음.
- **OS(facts) 변경 승인 절차 폐지 → WEB/WAS와 동일한 읽기 전용 이력으로 전환** — 기존엔 `FactFieldDefinition.requires_approval`로 지정한 필드만 값이 바뀌면 `PendingChange`로 대기, 대시보드/admin에서 승인해야 반영됐음. 이제 웹설정/WAS와 동일하게 push 즉시 반영하고, 이미 존재하는 자산의 AUTO/FIXED 필드 값이 실제로 바뀐 것만 신규 `FactChangeHistory`(field 선택 없이 전부 무조건 기록 — WEB/WAS가 설정 내용 전체를 선택 없이 기록하는 것과 동일 원칙)에 조회용으로 남긴다. `requires_approval` 체크박스와 그 지정 전용이던 `FactFieldDefinition.Source.FIXED`(고정 컬럼 8개를 승인 대상으로 지정하기 위한 메타데이터 값)도 선택할 대상 자체가 없어져 함께 삭제. `facts/approval.py`를 `facts/history.py`로 재작성(`record_fact_changes()`가 push 직전 값 비교 + 이력 기록만 담당, 실제 반영은 기존 로직이 그대로 함, 값이 하나라도 바뀌면 `Asset.last_changed_at`도 갱신). 대시보드 `/dashboard/changes/`는 체크박스 일괄 승인/반려·상태 필터를 전부 제거하고 webconfig/was 변경 이력과 같은 골격(자산/필드/이전값/새값/감지시각)으로 재작성, admin의 승인/반려 액션도 제거. 전환 시점에 `PendingChange`가 0건이라 데이터 이관 없이 모델 자체를 교체(`FactChangeHistory` 신규 생성 + `PendingChange` 삭제). `samples/facts/drnrap01.json`을 값 일부 바꿔 재push해 즉시 반영 + 이력 기록 + `last_changed_at` 갱신까지 실제로 확인.

## 1.0.37

- **웹설정/WAS에 설정 파일 경로 표기 추가** — WEB(WebToB/Apache/Nginx)·WAS(JEUS/JEUS6) 6개 kind 전부 AWX가 설정을 읽어온 원본 경로를 `config_path`로 같이 push하도록 확장. AWX 플레이북은 이미 `slurp`용 경로 변수(`webtob_config_path` 등)를 갖고 있어 payload에 한 줄만 추가(JEUS6만 파일이 여러 개라 `jeus6_config_dir`, 즉 디렉터리 값을 대신 저장). `WebConfigSource.config_path`/`WasConfigSource.config_path` 신규 필드(AUTO, `solution_version`과 동일하게 payload에 값이 없으면 기존 값 유지 — 롤아웃 중 값이 안 사라지게). 웹설정/WAS 상세 페이지 소제목과 목록 화면(최근 변경일/최근 반영일 바로 앞, 정렬 불가 컬럼)·엑셀 다운로드·admin 목록에 노출. **폐쇄망 반입 시 `push_webtob_config_to_cmdb.yml`/`push_apache_config_to_cmdb.yml`/`push_nginx_config_to_cmdb.yml`/`push_jeus_config_to_cmdb.yml`/`push_jeus6_config_to_cmdb.yml` 5개 플레이북 파일을 AWX Project에 다시 반입(동기화)해야 함 — 값 자체는 AUTO+optional이라 Job Template에 새 변수를 추가할 필요는 없음.**
- **WebToB vhost 목록의 SSL 컬럼명을 Apache/Nginx와 통일** — Apache/Nginx vhost 목록은 이미 "SSL"(플래그)/"SSL 인증서"/"SSL Protocols"/"SSL Ciphers" 4컬럼으로 갖춰져 있는데 WebToB만 플래그+인증서가 한 컬럼에 섞여 있고 Cipher 컬럼명도 "SSL RequiredCiphers"로 달랐음. WebToB는 SSL 절 이름이 있다는 차이만 살려("이름 (인증서 경로)") 나머지는 동일한 4컬럼 구조로 맞춤(`/dashboard/webconfig/vhosts/` 화면·엑셀 다운로드, 상세 모달의 WebToB SSL 카드도 함께 통일).

## 1.0.36

- **JEUS6 한 호스트에 여러 인스턴스(계정별) 설치 지원** — 같은 물리 호스트에 OS 계정만 다르게 해서 JEUS6가 여러 개 뜨는 경우(예: `ddorap01`에 `jeuscm`/`jeuslt` 각각), 기존 `(asset, kind)` 유니크 키로는 두 번째 push가 첫 번째를 덮어쓰는 문제가 있었음(설정 내용만으론 인스턴스를 구분할 방법이 없어 발견 후 즉시 수정, 실사용 전 반영). `WasConfigSource.instance_name`(AWX가 payload에 명시적으로 실어 보내는 OS 계정명 등 식별자) 신규 필드로 유니크 키를 `(asset, kind, instance_name)`로 확장. `kind=jeus`는 항상 빈 문자열이라 기존 동작 그대로. WAS 목록/JEUS 컨테이너 목록/엑셀 다운로드/상세 화면에 "인스턴스" 컬럼 추가. `awx/push_jeus6_config_to_cmdb.yml`은 `jeus6_instance_name` 변수를 필수로 요구하도록 갱신 — **폐쇄망 반입 시 기존 jeus6 Job Template에 이 변수를 추가해야 함**.

## 1.0.35

- **JEUS6(`kind=jeus6`) WAS 설정 파싱 신규 지원** — `JEUSMain.xml`(노드/도메인 레벨) + 컨테이너별 `servlet_engine{N}/WEBMain.xml`(웹 커넥션) 조합을 파싱해 기존 JEUS 7+(`kind=jeus`)와 동일한 컨테이너/WebToB 연결/데이터소스(1.0.34에서 추가된 `JeusDataSource`) 화면으로 보여준다. JEUS6은 admin 서버 개념이 없어(노드마다 자기 `JEUSMain.xml`을 따로 가짐) 호스트 판별을 `<node><name>`으로 직접 하고, AWX도 admin 서버 한 대가 아니라 JEUS6 노드 전부를 대상으로 push해야 함(`awx/push_jeus6_config_to_cmdb.yml` 신규). 파일이 여러 개라 CMDB API는 이 kind에 한해 `content`(단일 문자열) 대신 `files`(파일명→원본 텍스트 dict)를 받는다. `servlet_engine{N}`의 `N`은 컨테이너 이름이 아니라 `<engine-command><name>engine{N}</engine-command>`의 엔진 번호와 매칭. `JeusDataSource`는 JEUS6엔 컨테이너별 참조가 파일에 없어 그 노드의 모든 컨테이너에 일괄 연결(식별자도 `data-source-id`가 없어 `export-name`으로 대체). `samples/jeus6/` 실제 재push로 검증.

## 1.0.34

- **자산 상세 "연결된 시스템" 표 500 에러(ORA-00932) 수정** — 폐쇄망 반입 후 시스템 push된 자산의 상세 화면을 열면 500 에러가 난다는 제보. `dashboard/queries.py`의 `get_system_hosts_for_vms()`가 `annotate(Count("vms", distinct=True))` + `select_related("source")` 조합인데, 목록 화면(`get_system_host_queryset`)과 달리 `SystemHost.extra`/`SystemSource.raw_response`(JSONField→Oracle NCLOB)를 `defer()`로 빼지 않아 GROUP BY에 NCLOB 컬럼이 끌려들어가 발생. 목록 화면과 동일하게 `.defer("extra", "source__raw_response")` 추가.
- **WAS 상세에 컨테이너별 Data Source 정보 추가** — domain.xml의 `<resources><data-source>`(도메인 레벨 JDBC 커넥션 풀 정의)를 새 모델 `JeusDataSource`로 파싱해, 각 컨테이너가 참조하는 데이터소스(ID/Vendor/DB 접속 정보/User/Pool min·max)를 상세 화면 컨테이너 카드에 표로 노출. 하나의 데이터소스를 여러 컨테이너가 공유할 수 있어 WebToB의 SvrGroup↔VHost와 같은 이유로 M2M으로 연결. 비밀번호는 설정 파일에 암호화된 값으로 있어도 민감정보라 CMDB엔 아예 저장하지 않음.

## 1.0.33

- **Nutanix 시스템 push 실패 추가 수정 - 같은 VM이 payload에 중복 보고되는 경우 방어** — 1.0.32의 필드명 수정 후에도 `unique_system_vm_uuid_per_host` 위반이 재발. 원인은 필드명이 아니라 같은 `(host, uuid)`가 `vms_payload` 안에 두 번 이상 들어오는 실제 데이터(Nutanix DR/Metro 이중화로 보호되는 VM이 클러스터 관점별로 중복 보고되는 것으로 추정, `protectionType: PD_PROTECTED`)였음. `systems/sync.py`의 `sync_systems()`가 이제 uuid가 실제 값인 중복은 나중 값으로 덮어쓰고(SystemHost upsert와 동일한 "나중 값이 이긴다" 원칙), uuid가 비어있는(host 매칭 자체가 안 된) 항목은 기존처럼 각각 별도로 남기도록 수정. vCenter push도 같은 함수를 공유해 동일하게 보호됨.
- **Nutanix 시스템 push가 호스트/VM 50대까지만 수집되던 문제 수정** — `push_nutanix_systems_instance_tasks.yml`이 목록 조회 API를 파라미터 없이 한 번만 호출해 v4 API의 페이지네이션 기본값(환경 실측 50건)만 가져오고 나머지는 조용히 잘렸음. `$page`(0-base)/`$limit=100`을 명시하고, 1페이지 응답의 `metadata.totalAvailableResults`로 전체 개수를 계산해 남은 페이지를 마저 가져오도록 수정(1페이지로 충분하면 추가 호출 없음). 호스트/VM 둘 다 동일하게 적용.

## 1.0.32

- **Nutanix 시스템 push 실패 수정 - AHV 호스트/VM 필드명 스네이크케이스 오타** — `push_nutanix_systems_instance_tasks.yml`이 Prism Central v4 API 필드를 `ext_id`/`host_name`/`power_state`(스네이크케이스)로 짐작해 읽었으나 실제 응답은 전부 카멜케이스(`extId`/`hostName`/`powerState`, VM의 호스트 참조는 `vm.host.extId`)라 Jinja가 조용히 `Undefined`→`default('')`로 넘어가면서 모든 host의 `external_id`/모든 vm의 `uuid`가 빈 문자열로 저장됨 → `(host, uuid)` 조합이 전부 겹쳐 실제 운영 push에서 `ORA-00001(unique_system_vm_uuid_per_host)`로 실패. 실제 Prism Central 응답으로 필드명을 재검증해 수정.

## 1.0.31

- **시스템 목록에 베어메탈(물리) 장비 수기 등록 기능 추가** — vCenter/Nutanix push로만 채워지던 "시스템" 탭에, push 경로가 없는 베어메탈 장비를 대시보드에서 직접 등록/편집/삭제하는 기능 신설(`SystemSource.Kind.PHYSICAL`). 소스 이름은 전산실/그룹별로 직접 입력해 관리하고, 자산 미확정 상태(발주/랙 설치만 된 장비)로 먼저 등록한 뒤 나중에 hostname으로 연결하는 것도 지원. vCenter/Nutanix가 보고하는 행은 지금처럼 push 전용 읽기 전용 유지.
- **물리 장비의 AUTO 필드(CPU/제조사 등)를 vCenter/Nutanix와 같은 라벨로 편집 가능하게 확장** — 물리 kind는 push 자체가 없어 자동 추출값이 다음 push에 덮어써질 위험이 없다는 점에 착안, 셀 클릭 편집과 엑셀 업로드 둘 다 물리 소스 행에 한해 AUTO 필드 반영을 허용(vCenter/Nutanix 행은 계속 차단돼 값이 무시됨).
- **시스템 상세에 "원본 응답 보기" 추가** — admin에서 System host field definition을 새로 등록할 때 dot-path를 찾기 쉽도록, 자산 상세와 같은 패턴으로 `SystemHost.extra` 원본 JSON을 접이식 박스로 노출.
- **오라클 호환 가이드에 JSONField NCLOB 위험 명시** — Oracle Django 백엔드가 JSONField도 TextField와 동일하게 NCLOB로 매핑한다는 걸 확인해, 지금까지 TextField만 언급하던 CLAUDE.md 문구를 JSONField까지 포함하도록 확장(코드 변경 없음, 검증 절차 문서화).

## 1.0.30

- **서비스 탭 저장 후 화면 갱신 안 되는 문제 수정** — WebToB↔JEUS로 연결된 쪽은 저장 시 반대쪽 표(WEB↔WAS)의 행도 서버에서 같이 바뀌는데, 지금까지는 편집한 셀 하나만 JS로 patch해서 반대쪽 표는 새로고침 전까지 예전 값으로 보였음. 저장 성공 시(일반/충돌 확인 후 강제 저장 둘 다) 셀 patch 대신 페이지를 새로고침해 두 표 모두 최신 상태로 맞춤.

## 1.0.29

- **AUTO 필드 dot-path가 리스트 중간 경로를 숫자 인덱스로 진입 가능하도록 확장** — `extract_json_path`(`facts/dynamic_fields.py`)가 지금까지 경로 중간에 JSON 리스트가 나오면 무조건 `None`을 반환해(인덱싱 미지원) Windows facts의 MAC 주소(`ansible_facts.interfaces`가 리스트라 `default_ipv4` 같은 평평한 경로가 없음)를 못 뽑는 문제가 있었음. `interfaces.0.macaddress`처럼 숫자 세그먼트로 리스트 인덱스 진입을 지원(조건 필터링/전체 순회는 여전히 미지원 — "필드 하나=값 하나" 원칙 유지). `systems` 앱도 같은 순수 함수를 재사용하고 있어 vCenter/Nutanix의 리스트 기반 원본에도 동일하게 적용됨. `samples/awx/windows.json` 재push로 검증.
- **서비스 탭에서 서비스명 저장 시 ORA-00932 수정** — WebToB↔JEUS 서비스 전파(`was/linkage.py`의 `get_connected_containers`)가 `JeusContainer.objects.filter(...).distinct()`를 쓰는데 `JeusContainer.deployed_apps_summary`(TextField→Oracle NCLOB)가 SELECT 컬럼에 그대로 포함돼 폐쇄망(Oracle)에서만 저장 시 500이 나던 문제. SvrGroup-vhost M2M 조인이라 `.distinct()` 자체는 필요해 이번엔 `defer("deployed_apps_summary")`로 그 컬럼만 뺌(이 함수는 해당 값을 쓰지 않음).

## 1.0.28

- **WAS kind=jeus 표시 라벨을 "JEUS 7+"에서 "JEUS"로 단순화** — jeus6만 구분되면 충분하다는 판단, "7+" 범위 표기 불필요.
- **WEB kind=webtob 표시 라벨을 "WebtoB"에서 "WEBTOB"로 통일** — 구성도 WEB 노드 라벨도 하드코딩 문자열 대신 `source.get_kind_display()`로 통일해서 이후 라벨이 또 바뀌어도 모델 한 곳만 고치면 되게 정리(Apache/Nginx 노드 라벨도 같은 방식으로 전환, 값 동일).

## 1.0.27

- **구성도 그림 안 노드/박스 클릭 시 상세 모달 신규** — Graphviz의 `URL` 속성(노드/클러스터에 지정하면 SVG 출력에서 해당 도형이 `<a>`로 감싸짐)을 이용해 WEB/WAS 박스는 WEB/WAS 설정 상세, OS 박스는 자산 상세, System 박스는 시스템 상세로 연결. 구성도 페이지가 다른 화면의 모달에 끼워지는 화면이 아니라 독립 페이지라 서비스 탭과 같은 fetch+모달 패턴을 그대로 재사용(URL 경로 패턴으로 어떤 상세인지 판별).
- **구성도 OS 박스 라벨 개선** — "OS"라는 고정 문구 대신 실제 os_family(RedHat/AIX/Windows 등, `asset.hostfact.os_family`)를 보여주고, Hostname 옆에 `(IP)`를 같이 표시(`asset.primary_ip`). facts 미수집 등으로 값이 없으면 기존처럼 "OS"/IP 생략으로 폴백.
- **구성도 확대/축소 버튼 추가** — SVG는 벡터라 확대해도 화질 저하가 없어, `−`/`기본값`(100%로 초기화)/`+` 버튼으로 클라이언트에서 크기를 조절한다(서버 렌더링은 그대로, `<svg>`의 width/height를 스케일만큼 재계산). 마우스 휠/드래그 제스처 대신 큼직한 버튼 클릭으로 통일 — 고대비/큰 글씨 등 저시력 사용자를 고려해온 이 프로젝트의 기존 디자인 톤에 맞춤.
- **WAS `kind` 재정리: `jeus8` → `jeus`(표시 라벨 "JEUS 7+")** — domain.xml 레이아웃이 같은 JEUS 7/8/8.5/9를 kind 하나로 묶고, 파일 구조 자체가 다른 JEUS 6는 향후 `kind=jeus6`로 분리하기 위한 사전 정리(JEUS 6 파서는 아직 미구현). `kind`는 파서 선택용 키, 실제 세부 버전은 기존처럼 `solution_version`이 담당해 역할이 겹치지 않음. 기존 데이터는 마이그레이션으로 `jeus8`→`jeus` 일괄 전환. 관련 URL(`/dashboard/was/jeus/containers/`)·AWX 플레이북(`awx/push_jeus_config_to_cmdb.yml`, payload `kind: jeus`)·화면 라벨("JEUS8 목록"→"JEUS 목록") 전부 개명 — **폐쇄망 반입 시 AWX Job Template의 플레이북 경로를 새 파일명으로 갱신해야 함**(파일명이 바뀜).

## 1.0.25

- **서비스 탭 "구성도" 이동을 버튼 컬럼으로 분리** — 지금까지 서비스명 편집 셀 안에 작은 텍스트 링크로 같이 있던 "구성도"를 서비스명 왼쪽 별도 컬럼의 버튼(`is-light is-small`)으로 이동. 편집용 클릭 영역과 페이지 이동 액션이 한 셀에 섞여 있던 걸 분리(WEB/WAS 표 둘 다 적용, 서비스 미배정 행은 버튼 숨김).
- **서비스 탭에서 Hostname/솔루션 클릭 시 상세 모달 신규** — WEB 표의 Hostname은 자산 상세(`asset-content`), 솔루션은 WEB 설정 상세(`webconfig-content`)를, WAS 표의 Hostname은 자산 상세, 종류는 WAS 설정 상세(`was-content`)를 각각 AJAX로 fetch해 모달로 보여준다(웹설정/WAS 목록 화면이 이미 쓰던 행 클릭→모달 패턴을 셀 단위로 재사용). 자산 미매칭 컨테이너(`asset=null`)는 기존처럼 "(미등록)" 텍스트만 표시.

## 1.0.24

- **구성도 화면 500 에러(ORA-00932) 수정** — `build_service_topology_graph`의 `JeusWebtobConnector` 조회가 `select_related("container")`로 `JeusContainer.deployed_apps_summary`(TextField→Oracle NCLOB)를 SELECT 컬럼에 끌어온 채 `.distinct()`를 걸어 폐쇄망(Oracle)에서만 500이 나던 문제. 코드상 `connector.container_id`만 쓰고 `connector.container`는 참조하지 않아 `select_related("container")` 자체가 불필요했던 것 확인 후 제거(`.distinct()`는 M2M 조인으로 인한 중복 제거에 계속 필요해 유지).

## 1.0.23

- **서비스명이 자유 텍스트에서 `core.Service` FK로 전환** — WebtobVhost/ApacheVhost/NginxVhost/JeusContainer가 같은 Service 행을 참조하게 해서 WEB/WAS 양쪽 서비스명이 오타로 어긋나는 걸 원천 차단(기존 값은 데이터 마이그레이션으로 이관). 부수적으로 서비스 조회 화면에서 Apache/Nginx 서비스명 수정이 원본 vhost에 반영 안 되던 버그도 수정.
- **서비스 배정 편집을 "서비스" 탭 한 곳으로 통합** — WEB(도메인 기준)·WAS(컨테이너 기준) 표를 한 페이지에 배치하고 여기서만 수정, WebToB/Apache/Nginx vhost 목록·JEUS8 컨테이너 목록·상세 모달의 인라인 편집은 전부 읽기 전용으로 전환. WebToB↔JEUS로 실제 연결된 쪽은 한쪽만 고쳐도 반대쪽까지 즉시 같이 맞춰지고(연결된 쪽에 이미 다른 서비스명이 있으면 확인 후 반영).
- **"구성도" 신규**(`/dashboard/services/topology/`, "서비스" 드롭다운 하위) — 서비스 하나를 골라 System→OS→WEB/WAS 연결을 Graphviz로 그린 실제 그림으로 보여준다. 같은 물리 서버/OS는 한 번만 그려지고 WebToB↔JEUS 실제 연결만 화살표로 표시 — OS가 이중화된 경우에도 어떤 게 같은 서버인지 명확함(표 방식은 레인마다 서버가 반복 표시돼 기각). WEB vhost 노드에는 도메인·포트·TLS 여부(http/https)까지 같이 표시.
  - Docker 이미지에 `graphviz`(apt) 최초로 추가 — 서버에서 `dot` 서브프로세스로 SVG를 그려 내려주는 방식이라 클라이언트 JS 의존성이 없음.

## 1.0.22

- 시스템 목록/자산 상세의 "연결된 시스템" 표에 "소스"(vCenter/Nutanix 인스턴스명) 컬럼 신규 — 물리 호스트 이름(예: `DRNRAP01`)이 OS hostname과 달리 여러 인스턴스에 걸쳐 유일하다는 보장이 없어(엑셀 매칭 키가 애초에 `(source_name, name)` 복합키였던 이유와 동일), 이름 하나만 보여주면 오해 소지가 있어 소스를 이름보다 앞(더 넓은 범위)에 배치
- WEB(웹설정/WebToB/Apache/Nginx vhost 목록)·WAS(WAS/JEUS8 컨테이너 목록) 6개 화면 전부 Hostname 오른쪽에 IP 컬럼 추가 — 설정 파일 자체엔 IP 정보가 없어, hostname과 마찬가지로 이미 연결된 Asset(facts로 등록된 자산)의 `primary_ip`를 그대로 재사용(JEUS8만 `source.asset`이 아닌 `container.asset` 기준, 다른 화면과 동일하게 Hostname 컬럼이 참조하는 asset을 그대로 씀)

## 1.0.21

- **"시스템" 신규** — vCenter/Nutanix가 보고하는 물리 장비(ESXi 호스트/AHV 노드) 인벤토리를 시각화하는 `systems` 앱 추가. 개별 호스트 facts push와 완전히 분리된 흐름으로, AWX가 `hosts: localhost`에서 vCenter/Nutanix API를 직접 호출해 물리 호스트+VM 목록을 배치로 CMDB(`POST /api/systems/`)에 push하고, VM은 hostname으로 기존 facts 자산과 매칭한다(자산 신규 생성은 안 함)
  - 모델: `SystemHost`(물리 장비, "시스템" 탭 기본 단위) ← `SystemVm`(VM=OS 인스턴스, host/asset 둘 다 매칭 실패 시 null 허용) ← `SystemDisk`/`SystemNic`
  - `SystemHost`도 facts처럼 admin 등록만으로 컬럼을 늘리는 동적 필드(`SystemHostFieldDefinition`/`SystemHostFieldValue`) 지원 — AUTO(extra에서 dot-path 추출, kind별 경로 override 가능)/MANUAL(선택형 포함) 둘 다 지원
  - 자산관리 관점에서 "어떤 OS가 어느 물리 시스템에 있나"를 보기 쉽도록, 시스템 상세의 VM 표는 OS 목록과 동일한 컬럼으로, 자산 상세의 "연결된 시스템" 표는 시스템 목록과 동일한 컬럼으로 서로의 화면을 그대로 재사용해서 보여줌
  - AWX 플레이북 신규: `push_vcenter_systems_to_cmdb.yml`/`push_nutanix_systems_to_cmdb.yml`(여러 인스턴스 순회 가능) — vCenter/Nutanix 응답의 세부 스키마(호스트 하드웨어 스펙 등)는 버전마다 달라 실측 검증 전이라 우선 `extra`에 원본을 보관하고 필요한 만큼만 admin에서 동적 필드로 노출하는 구조로 시작

## 1.0.20

- 자산 엑셀 다운로드에 IP/OS 컬럼 누락 수정 — `hostname`+동적 필드(AUTO/MANUAL)만 내보내던 기존 로직에 `IP`(`primary_ip`)/`OS`(`os_family`)를 참고용 컬럼으로 추가(hostname 바로 뒤). AUTO 필드와 같은 취지로 업로드 시엔 항상 무시(편집 대상 아님) — 다운로드 그대로 재업로드해도 에러 없이 통과

## 1.0.19

- 대시보드 전 화면(자산/WEB/WAS 목록·상세, 변경 이력, 엑셀 업로드 결과 등 18개 템플릿) 공통으로 자산 hostname을 대문자로 표시 — 저장값은 기존처럼 소문자 그대로 유지하고 화면 표시만 CSS(`dash-hostname`, `text-transform: uppercase`)로 바꿔서 검색/API 매칭에는 영향 없음. 브라우저 탭 제목처럼 CSS가 안 먹히는 곳은 `|upper` 필터, JS로 조립하는 모달 제목은 `.toUpperCase()`로 처리. vhost 자체의 `hostname`(도메인) 필드는 별개 개념이라 대상에서 제외
- OS 목록 검색에 `os_family` 추가(예: "Windows"/"RedHat"으로 검색 가능) — 검색창 placeholder도 "hostname/IP/OS"로 갱신
- WEB/WAS 목록 검색에 종류(`kind`) 추가 — 원시값(webtob/apache/nginx/jeus8)뿐 아니라 표시 라벨("JEUS 8"처럼 원시값과 다른 경우)로 검색해도 매칭되는 공용 헬퍼(`_kind_search_q`) 신설

## 1.0.18

- Windows 자산의 OS 관련 필드 오적재 수정: `HostFact.os_family`가 `ansible_facts.distribution`(윈도우에선 "Microsoft Windows Server 2022 Standard" 같은 풀네임) 대신 표준 `os_family` 키를 쓰도록 변경, `os_version`은 Windows일 때만 `distribution`(마케팅명)을 쓰고 그 외엔 기존처럼 `distribution_version`을 쓰도록 분기 — 관련 추출 로직을 `facts/views.py`/`facts/approval.py` 두 곳 중복 정의에서 `facts/approval.py`의 `FIXED_FIELD_EXTRACTORS`/`compute_fixed_values()` 한 곳으로 통합
- `Asset.primary_ip` 추출이 Windows ansible facts엔 없는 `default_ipv4`에만 의존해 IP가 빈 값으로 저장되던 문제 수정 — 없으면 `interfaces[].default_gateway`가 걸린 인터페이스의 `ipv4.address`로 폴백
- `FactFieldDefinition`에 `os_family_key_overrides`(JSON) 신규 — AUTO 동적 필드가 os_family별로 다른 raw facts 경로를 써야 할 때(예: OS버전) 값이 실제로 다른 os_family만 등록하면 되고 나머지는 기존 `key`를 그대로 씀. push 시점(`sync_dynamic_fields`)과 소급 백필(`backfill_field`) 둘 다 지원

## 1.0.17

- 통합대시보드 신규 — 상단 "CMDB" 로고 클릭 시 이동(`/dashboard/`, 이전엔 연결된 화면이 없어 404였음). OS/WEB/WAS를 카테고리별 개수 타일로 한눈에 보여주고, 타일을 누르면 그 아래 도넛 차트로 하위 분포(OS는 버전, WEB/WAS는 솔루션 버전)를 펼쳐 보여준다. 세 섹션 다 같은 코드(`_build_category_tiles`/`_breakdown_by_field`)를 공유해서 나중에 섹션이 늘어나도 뷰에 한 줄만 추가하면 됨
- 자산 상세를 모달 대신 실제 페이지(`/dashboard/assets/<pk>/`)로 신규 — 메인 목록과 같은 컬럼(동적 필드 포함)을 가로 스크롤 대신 세로 표로 보여줌. admin에서 필드를 추가/변경해도 코드 수정 없이 그대로 반영됨. 원본 facts는 접어서(`<details>`) 유지, 편집은 목록 화면에서만(중첩 모달 방지)
- WebToB vhost의 Logging/ErrorLog가 `*LOGGING`절 엔트리 이름(예: `log1`) 대신 실제 로그 경로를 보여주도록 수정 — 이름을 못 찾으면 기존처럼 이름값으로 폴백
- Apache/Nginx vhost에도 WebToB처럼 SSL Protocols/Ciphers 노출. `<VirtualHost>`/`server{}` 안에 값이 없으면 전역(mod_ssl 공통 설정/`http{}`) 값으로 폴백. WebToB의 "SSL RequiredCiphers" 컬럼 정렬은 제거(TextField/Oracle NCLOB이라 `ORA-00932` 위험 — Apache/Nginx의 동일 컬럼은 처음부터 정렬 미노출로 설계)
- 엑셀 다운로드가 없던 화면 10개(변경 이력/WEB 목록·변경 이력/WebToB·Apache·Nginx vhost 목록/WAS 목록·변경 이력/JEUS8 컨테이너 목록/어플리케이션)에 다운로드 버튼 추가 — 검색 필터 무시하고 항상 전체 데이터
- 자산 MANUAL 필드 엑셀 다운로드/업로드가 이제 AUTO 필드도 참고용으로 같이 싣는다(편집은 여전히 MANUAL만 반영) — AUTO 컬럼이 섞인 채로 재업로드해도 더 이상 에러 나지 않음
- WAS(JEUS8) 컨테이너의 "배포된 앱" 표시가 `context-path`(대부분 `/`라 앱 구분이 안 됨) 대신 실제 배포 경로(`path`)를 `id`와 함께 보여주도록 수정

## 1.0.16

- WAS(JEUS 8) 설정 파싱 추가 — 신규 `was` 앱, `POST /api/was/`(`kind=jeus8`)가 domain.xml을 파싱해 컨테이너(`<server>`) 단위로 노출. 대시보드에 `/dashboard/was/`(공통 목록), `/dashboard/was/jeus8/containers/`(JEUS8 컨테이너 목록), `/dashboard/was/<pk>/`(상세), `/dashboard/was/changes/`(변경 이력) 신규 — 상단 내비게이션에 "WAS" 드롭다운 추가
- domain.xml 하나가 여러 물리 노드의 컨테이너를 담을 수 있지만 실제 수집은 도메인의 admin 서버 호스트에서만 이뤄지는 구조 반영 — push를 보낸 자산(admin 호스트)과 각 컨테이너가 실제로 속한 자산(컨테이너 자신의 node-name)을 분리해서 관리. 아직 자산으로 등록 안 된 노드의 컨테이너는 제외하지 않고 자산 미연결 상태로 저장, 해당 노드가 나중에 facts push되면 다음 JEUS push 때 자동 연결
- JEUS 컨테이너의 `webtob-connector`(WebToB 등록 정보)를 `webconfig` 앱의 WebToB 데이터와 실제로 교차 연결(`registration-id`↔WebToB `*SERVER` 이름, `network-address`↔자산 hostname/IP). 연결된 WebToB vhost의 서비스명이 하나로 겹치면(이중화 구성의 일반적인 경우) 컨테이너의 서비스명에 자동 반영, 여러 값으로 갈리거나 연결이 없으면 기존 수기 입력값 유지
- 신규 AWX 플레이북 `awx/push_jeus8_config_to_cmdb.yml` — 각 JEUS 도메인의 admin 서버 호스트에서만 실행해야 함(워커 노드 대상 금지)
- 솔루션 버전은 domain.xml 루트의 `version` 속성에서 명령어 실행 없이 바로 추출(WebToB/Apache/Nginx의 마커 방식과 다름)
- (문서) `awx/OS_SPECS.md` 신규 — AWX 관리 대상 OS별 Python/PowerShell 요구사항 기록(AIX/Linux는 Python 3.9 권장, Windows는 별도 요구사항)

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
