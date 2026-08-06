# 릴리즈 노트

이미지 버전(`VERSION`)별로 실제 배포되는 내용 위주로 정리한다. 새 버전은 위에 추가.
개발 과정의 세세한 디버깅/검토 기록은 `WORKLOG.md` 참고.

1.0.6까지의 이력은 이 파일 도입 전이라 별도 기록 없음 — `WORKLOG.md`의 해당 날짜 항목 참고.

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
