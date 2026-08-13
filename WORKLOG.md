# 작업 일지

일 단위로 진행한 작업을 기록한다. 새 날짜는 위에 추가한다.

## 2026-08-13

- **로컬 개발 환경 기동**: Docker Desktop이 꺼져있어 먼저 실행 후 엔진 준비될 때까지 대기, `docker compose up -d --build`로 기동 후 로그인 페이지 200 응답까지 확인(기존 pgdata 볼륨 재사용이라 이전 세션 데이터 그대로 남아있음)
- **vCenter 시스템 push 플레이북(`push_vcenter_systems_to_cmdb.yml` 계열) AWX 실행 오류 3건 연쇄 수정** — 실제 AWX Job Template으로 처음 돌려보면서 순차적으로 발견
  1. **`'loop' is not a valid attribute for a Block`**: VM별 상세/게스트 조회 2개 API 호출을 `block:` + `loop:`로 묶으려 했는데 Ansible은 애초에 block에 loop를 지원하지 않음(근본적 문법 제약) — block 내용을 신규 `awx/push_vcenter_vm_detail_tasks.yml`로 분리해 `include_tasks` + `loop`로 대체. Nutanix 쪽(`push_nutanix_systems_instance_tasks.yml`)은 VM별 추가 API 호출이 필요 없는 구조라 애초에 이 함정을 안 밟았던 것도 확인
  2. **VM이 전부 host 미매칭(SystemHost의 "VM 수"가 항상 0)**: 사용자가 Django admin에서 실제 push된 SystemVm 레코드(RIMGDT01, TSSOAP01)를 확인해준 덕에 `vm_detail.json.host`(VM 상세 응답에서 소속 호스트를 가져온다고 짐작했던 필드)가 실제로는 존재하지 않는 필드였음을 확인 — VM.Info 구조엔 cdroms/disks/nics/identity 등만 있고 host 참조가 없음. `GET /api/vcenter/vm?hosts=<호스트ID>`로 호스트별 VM 목록을 역조회해 `vcenter_vm_host_map`(vm id → host id dict)을 만드는 방식으로 재설계(`subelements` lookup으로 호스트별 결과를 펼쳐서 누적)
  3. **`Unsupported property with name: filter.hosts`(400)**: 위 역조회 구현 시 쿼리 파라미터를 `filter.hosts=`로 짐작해 실패 — 원인 확인을 위해 해당 태스크만 임시로 `no_log: true`→`ignore_errors: true`로 바꿔 커밋/push해 실제 에러 메시지 노출(세션 토큰이 잠깐 로그에 남는 정도라 위험 낮다고 판단), 사용자가 vSphere apiexplorer(vCenter 7.0.3)의 `GET /api/vcenter/vm` Parameters 목록을 캡처해줘서 실제 파라미터명이 `filter.hosts`가 아니라 `hosts`(구버전 `/rest/...` API의 `filter.` 접두사 관례가 신형 `/api/...`엔 없음)임을 확인 — 수정 후 `no_log: true` 원복
  - 세 번 모두 로컬 테스트로는 재현 불가(vCenter 실 API 필요)라 사용자가 AWX 잡 로그/apiexplorer 스크린샷을 캡처해주는 식으로 실측 기반 수정 반복 — awx/README.md에도 각 단계의 원인과 근거를 상세히 기록해둠
- **vCenter 물리 호스트 하드웨어 스펙(클러스터/CPU/메모리/모델/ESXi버전) 수집 불가 확인**: 호스트 매핑 정상화 후 "SystemHost의 extra가 너무 부실하다"는 지적으로 apiexplorer의 `GET /api/vcenter/host`(목록)/`GET /api/vcenter/host/{host}`(상세) 둘 다 확인한 결과 실제로 `host`/`name`/`connection_state`/`power_state` 4개 필드가 전부임을 실측 확인 — vSphere Automation API(신형 REST)에 하드웨어 스펙 자체가 없고, 얻으려면 구버전 SOAP API(vim25, PowerCLI가 쓰는 것과 동일)가 필요해 범위가 훨씬 커짐. 사용자와 상의해 이번엔 SOAP 연동 없이 현재 상태로 마무리하기로 결정 — awx/README.md에 "확인 종료"로 기록해 다음에 같은 조사를 반복하지 않도록 함

## 2026-08-11

- **통합대시보드 도넛 드릴다운에 버전별 목록 모달 추가(1.0.39)**: "종류 도넛에서 특정 버전 조각을 클릭하면 그 버전의 목록을 모달로 보여줄 수 있냐"는 요청으로 시작
  - 1차 구현은 새 뷰/템플릿(`OverviewDrilldownItemsView`, 자체 컬럼의 목록 fragment)으로 모달을 만들었으나, "기존 조회 화면(`/dashboard/assets/`·`/dashboard/webconfig/`·`/dashboard/was/`)을 그대로 활용해서 필터링만 걸어 모달로 띄우면 될 것 같다"는 피드백으로 전면 재설계 — 새 테이블을 안 만들고 실제 목록 화면에 정확 일치 필터(`os_family`/`os_version`, `kind`/`solution_version`, "버전 미상" 포함)를 추가해 그 화면을 iframe으로 모달에 그대로 불러오는 방식으로 교체(`get_asset_queryset`/`get_webconfig_queryset`/`get_was_config_queryset`, `describe_overview_filter()` 신규). 앞서 만든 뷰/템플릿/URL은 삭제
  - iframe이 "localhost에서 연결을 거부했다"는 제보로 원인 조사 — Django 기본 클릭재킹 방지(`X-Frame-Options: DENY`)가 자기 자신도 프레임에 못 넣게 막고 있던 것. `X_FRAME_OPTIONS = "SAMEORIGIN"`(같은 origin 내장만 허용, 실제 클릭재킹 방지는 유지)으로 해결
  - "모달 안에 표+페이지네이션만 남기고 싶다"는 후속 요청으로 `embed=1` 쿼리파라미터 도입 — `base.html`(내비게이션 숨김+여백 축소)과 세 목록 템플릿(제목/버튼/검색창/필터배너 숨김)에 반영, `{% querystring %}` 태그가 기존 GET 파라미터를 그대로 이어받는 걸 활용해 정렬/페이지네이션 링크에도 `embed=1`이 자동으로 유지되는 것까지 테스트 클라이언트로 확인
  - Django 테스트 클라이언트로 필터링된 건수가 도넛 집계(`get_*_version_breakdown`)와 정확히 일치하는지, embed 모드에서 실제로 표+페이지네이션만 남는지 검증 후 1.0.39로 배포(빌드/저장/zip/CHANGELOG/커밋/push/Release/오래된 첨부파일 정리까지 통상 절차대로 진행)
- **CLAUDE.md에 WORKLOG.md 자동 기록 절차 추가**: "이미지 버전 관리 같은 일련의 정리 작업을 할 때 WORKLOG는 말 안 하면 기록 안 해준다"는 지적 — "이미지 버전 관리" 절차에 CHANGELOG.md 작성 바로 다음 단계로 WORKLOG.md 기록을 추가(세션 종료 신호를 기다리지 않고 배포 준비 시점에 같이 기록), "세션 종료" 절차 1번은 그 시점 이후 추가된 작업만 이어서 정리하도록 문구 조정 — 이번 세션에 놓친 1.0.39 작업 내용도 이 문서에 소급 반영

## 2026-08-10

- **웹설정/WAS 설정 파일 경로 표기 신규(1.0.37)**: "WEB/WAS 설정 수집 요건이 동일한데 설정파일 경로도 같이 표기해달라"는 요청 — 코딩 전 검토부터 진행. `webconfig`/`was` 앱의 모델·시리얼라이저·뷰·AWX 플레이북 5개(webtob/apache/nginx/jeus/jeus6)를 먼저 다 읽어보고, **AWX 플레이북이 이미 설정 파일을 `slurp`할 때 쓰는 경로 변수(`webtob_config_path` 등, 전부 `default()` 기본값 있음)를 갖고 있는데 payload엔 안 실려 있고 버려지고 있다**는 걸 확인 — 새로 알아낼 게 없어 난이도가 낮다는 점을 검토 결과로 먼저 보고
  - JEUS6만 파일이 여러 개(`JEUSMain.xml` + `servlet_engine{N}/WEBMain.xml`)라 "파일 경로 하나"로 안 떨어지는 문제를 짚고, 디렉터리(`jeus6_config_dir`) 하나만 저장하는 절충안을 제시해 승인받음
  - 목록 화면 컬럼 추가 여부를 `AskUserQuestion`으로 확인(상세 페이지만 vs 목록도 추가) — "목록에도 추가"로 결정
  - `WebConfigSource.config_path`/`WasConfigSource.config_path`(CharField, `solution_version`과 동일한 롤아웃 안전 원칙 - payload에 값 없으면 기존 값 유지) 신규 필드 + 마이그레이션, 시리얼라이저/뷰/AWX 플레이북 5개/대시보드 상세·목록 템플릿/엑셀 다운로드(`dashboard/list_export.py`)/admin `list_display`까지 전부 반영
  - `samples/webtob/APCS01_http.m`/`samples/jeus8/domain.xml`을 실제 `POST /api/webconfig/`·`POST /api/was/`로 재push해 `config_path` 저장 확인, `config_path` 없이 재push해서 기존 값이 안 지워지는 것도 확인. Django test client로 목록/상세/엑셀 다운로드/admin 페이지 전부 200 + 값 렌더링 확인. `config_path`는 CharField(Oracle VARCHAR2)라 기존 `defer("raw_content", ...)` NCLOB 방지 로직과 안 겹치는 것도 코드로 재확인(CLAUDE.md의 Oracle 점검 습관 유지)
  - CHANGELOG에 "폐쇄망 반입 시 AWX 플레이북 5개 재동기화 필요" 콜아웃 추가(과거 1.0.35/1.0.36 항목의 관례를 따름) — 값 자체는 AUTO+optional이라 Job Template에 새 변수 추가는 불필요
  - 커밋 전 확인 단계에서 후속 요청 두 건 추가: (1) 목록의 "설정 경로" 컬럼을 최근 변경일/최근 반영일 **앞**으로 이동(웹설정/WAS 목록·엑셀 다운로드 둘 다) (2) WebToB vhost 목록(`/dashboard/webconfig/vhosts/`)의 SSL 컬럼명을 이미 통일돼 있던 Apache/Nginx 쪽("SSL"/"SSL 인증서"/"SSL Protocols"/"SSL Ciphers" 4컬럼)에 맞춤 — WebToB만 플래그+인증서가 한 칸에 섞여 있고 Cipher 컬럼명도 "SSL RequiredCiphers"로 달랐던 걸 정리(SSL 절 이름은 WebToB 고유라 "이름 (경로)" 형태로 유지), 상세 모달 카드도 같이 통일. 중간에 "상단 웹설정 목록에도 SSL 프로토콜/Cipher 요약 컬럼을 추가해달라"는 요청이 있었으나(소스 하나에 vhost가 여러 개면 콤마 요약이 필요해 `attach_webconfig_ssl_summary` 헬퍼까지 작성) 사용자가 바로 취소해 되돌림 — 실제 반영된 건 위 두 가지뿐
- **성능 검토 요청 + 자산 목록 검색 Oracle 500 긴급 수정(1.0.38)**: "데이터가 점점 쌓일 텐데 성능 이슈 없는지 검토해달라(내부망 Oracle)"는 요청으로 코드 리뷰 진행 — `.distinct()` 쓰는 곳을 전부 grep해서 하나씩 select_related/defer 상태 대조. `get_asset_queryset()`(`dashboard/queries.py`)만 유일하게 `hostfact__raw_facts`(NCLOB) defer 없이 검색 시 `.distinct()`를 걸고 있는 걸 발견 — `str(qs.query)`로 실제 생성 SQL을 찍어 `SELECT DISTINCT`에 `raw_facts`가 포함되는 것까지 직접 확인해 확정. 나머지(webconfig/was/process/system_host 쿼리)는 이미 방어돼 있음도 같이 확인. 그 외 발견 사항(등급별): PendingChange/*Revision 테이블이 보존기간 없이 무한 누적 + 정렬 컬럼 인덱스 없음(🟠), `systems/dynamic_fields.py`의 `sync_host_fields()`가 vCenter/Nutanix 배치 push의 호스트 루프 안에서 필드 정의를 매번 재조회하는 N+1(🟡), webconfig/was/systems sync가 대체로 개별 `.create()` 루프라 push 규모가 커지면 왕복 비용이 선형 증가(🟡), 엑셀 다운로드가 필터 무시 전체 로드(🟢, 지금 규모엔 무해) — 이 중 긴급 버그만 즉시 조치하고 나머지는 보고만(다음 항목 진행하느라 이번 세션에 손 안 댐)
- **OS(facts) 변경 승인 절차 폐지(1.0.38, 같은 세션 이어서)**: 위 성능 검토 직후 "OS쪽도 WEB/WAS처럼 승인 없애고 이력만 보여주는 걸로 가능하냐"는 요청 — 코딩 전 현재 구조부터 다시 설명(`facts/approval.py`의 `PendingChange` 게이트 vs webconfig/was의 `*Revision` 즉시반영+기록). facts는 필드 단위 EAV라 "어느 필드까지 이력에 남길지" 결정이 필요해서 `AskUserQuestion`으로 확인 — "AUTO/FIXED 필드 전부 무조건 기록"으로 결정(WEB/WAS와 완전히 동일한 원칙, 기존 `requires_approval` 체크박스 재활용 옵션은 기각). 실제 DB 확인 결과 `PendingChange` 0건, `requires_approval` 지정 필드도 1개뿐이라 데이터 이관 부담 없이 깔끔하게 갈아엎을 좋은 타이밍이었음
  - `PendingChange` 삭제, 신규 `FactChangeHistory`(asset/field_key/field_label/old_value/new_value/detected_at) 추가 — field_definition을 FK로 안 두고 key/label을 스냅샷으로 저장(FIXED 8개 컬럼은 애초에 FactFieldDefinition 행이 없고, AUTO 필드도 나중에 정의가 바뀌어도 과거 이력의 라벨이 그대로 남아야 해서). `FactFieldDefinition.requires_approval`과 그 지정 전용이던 `Source.FIXED`도 선택 대상 개념 자체가 없어져 함께 삭제
  - `facts/approval.py` → `facts/history.py`로 재작성: `stage_governed_changes`/`apply_pending_change`/`reject_pending_change` 3개 함수를 `record_fact_changes()` 하나로 통합(push 직전 이전값 vs 새값 비교 + 이력 기록만 담당, 값 반영은 호출부의 기존 로직이 그대로 함). `FIXED_FIELD_LABELS` 신규(FIXED 컬럼은 이제 FactFieldDefinition이 없어 admin에서 라벨 관리가 안 되므로 하드코딩). 값이 하나라도 바뀌면 `Asset.last_changed_at`도 갱신(예전엔 승인 시점에 갱신하던 걸 이 시점으로 옮김)
  - `facts/views.py`의 `FactsIngestView`가 governed_fixed_keys/governed_dynamic_keys/exclude_keys 분기 없이 항상 즉시 반영하도록 단순화. `sync_dynamic_fields()`의 `exclude_keys` 매개변수도 더 이상 쓰는 곳이 없어 제거
  - 대시보드 `/dashboard/changes/`(`ChangeHistoryListView`)에서 체크박스 일괄 승인/반려·상태 필터·`PendingChangeDecisionView`/`BulkPendingChangeDecisionView`(+관련 URL 4개) 전부 삭제, 템플릿을 webconfig/was 변경 이력과 같은 골격(자산/필드/이전값/새값/감지시각 표)으로 재작성. `facts/admin.py`의 `PendingChangeAdmin`(승인/반려 액션)도 `FactChangeHistoryAdmin`(읽기 전용, add/change 권한 없음)으로 교체
  - `dashboard/excel_import.py`(자산 MANUAL 필드 다운로드)의 `.exclude(source=FIXED)`, `dashboard/queries.py`의 `get_dynamic_field_definitions()` 동일 exclude도 Source.FIXED 삭제에 맞춰 정리
  - `samples/facts/drnrap01.json`을 vCPU/OS버전 값만 바꿔 실제 재push로 검증: 값이 승인 없이 즉시 반영되는 것(HostFactValue/HostFact 직접 조회), `FactChangeHistory`에 AUTO 2건+FIXED 1건이 정확히 기록되는 것, `Asset.last_changed_at`이 갱신되는 것까지 전부 확인 후 원본 값으로 재push해 원복. Django test client로 변경 이력/자산 목록/엑셀 다운로드/admin 페이지 전부 200 확인
  - CLAUDE.md "변경 승인" 섹션을 "변경 이력"으로 전면 재작성(웹설정 승인 없는 이력 원칙과 문장 구조 통일), "신규 수집 항목 추가"의 FIXED 설명과 "대시보드" 섹션의 관련 문구도 같이 갱신

## 2026-08-06

- **Nutanix 시스템 push 연쇄 오류 조사 및 수정(1.0.32 → 1.0.33)**: AWX에서 Nutanix push를 처음 돌렸더니 "물리 호스트(AHV 노드) 목록 조회" 태스크가 404로 실패한다는 제보 스크린샷으로 시작, 이후 같은 기능을 두고 총 세 차례 원인이 바뀌며 이어진 조사
  - **1차: 404 원인** — `nutanix.base_url`이 실제로는 Prism Element(개별 클러스터) 주소(`10.150.13.101`)를 가리키고 있었음. 사용자가 공유한 Prism 웹 UI 스크린샷에서 실제 Prism Central은 별도 IP(`10.150.1.11`)로 떠 있는 걸 확인 — v4 API(`clustermgmt`/`vmm` 네임스페이스)는 PC에서만 서빙되므로 PE 주소로는 404가 당연했음. AWX 쪽 `nutanix.base_url` 설정을 PC로 교정하도록 안내(코드 변경 없음)
  - **2차: ORA-00001(`unique_system_vm_uuid_per_host`) 원인** — base_url을 고친 뒤 재시도했더니 호스트/VM 조회까지는 성공했지만 CMDB push 단계(`no_log: true`라 AWX 로그에선 안 보임)에서 실패. K8s 파드 로그(Django 트레이스백)로 정확한 에러 위치를 확인. 원인은 `push_nutanix_systems_instance_tasks.yml`이 Nutanix v4 API 필드를 `ext_id`/`host_name`/`power_state`(스네이크케이스)로 짐작해 읽었는데 실제 응답은 전부 카멜케이스(`extId`/`hostName`/`powerState`, VM의 호스트 참조는 `vm.host.extId`)였던 것 — Jinja가 존재하지 않는 속성을 조용히 `Undefined`로 넘기고 `default('')`가 삼켜버려 모든 host의 `external_id`/모든 vm의 `uuid`가 빈 문자열로 수렴, `(host, uuid)` 조합이 전부 겹쳐 발생. 정확한 필드명은 Nutanix 공식 문서(JS 렌더링이라 스키마 확인은 실패)가 아니라 **사용자가 직접 받아준 AWX 잡 로그의 실측 raw JSON**(`ok: [...] => (item=...)` 덤프)으로 확정 — `extId`/`hostName`은 확실히 카멜케이스임을 확인 후 수정(1.0.32)
  - **3차: 필드명 수정 후에도 재발** — 1.0.32 배포 후에도 같은 ORA-00001이 재발. `protectionType: PD_PROTECTED`, 인스턴스명이 `DR`인 정황을 근거로 "Metro/DR 이중화로 같은 VM이 중복 보고되는 경우"를 추정해 `systems/sync.py`의 `sync_systems()`에 `(host, uuid)` 중복 시 나중 값으로 덮어쓰는 방어 로직을 추가(로컬 Postgres에서 시나리오 테스트로 검증) — 그런데 사용자가 `samples/awx/job_168.txt`(잡 실행 로그 텍스트 파일)를 직접 저장소에 넣어주고 분석을 요청. Python으로 해당 로그의 VM/호스트 transform 태스크 출력을 파싱해 실제 `extId` 중복 여부를 전수 확인한 결과 **중복이 전혀 없음**을 확인 — 방금 추가한 dedup 방어는 이번 재발의 실제 원인이 아니었음을 인정
  - **진짜 원인**: `ok: [...] => (item=...)` 로그는 `set_fact`가 만든 변환 결과가 아니라 **루프 입력값(raw API 객체)을 그대로 echo**하는 것이라 실제 추출이 성공했는지는 이 로그만으론 알 수 없다는 점을 재확인. 사용자에게 "AWX Project가 참조하는 플레이북 파일을 CMDB 이미지 반입과 별도로 갱신했는지" 확인한 결과, **CMDB Docker 이미지만 반입하고 AWX 쪽 플레이북 사본은 갱신하지 않았던 것**으로 확인 — `awx/*.yml`이 이미지에 `COPY`는 되지만 AWX가 실제 실행하는 건 AWX Project에 등록된 별도 사본이라, 이미지 재배포만으로는 절대 반영되지 않는다는 구조적 함정이 근본 원인이었음(코드 버그 아님)
  - **부수 확인**: 사용자가 host 목록 덤프에서 "extId는 다른데 uuid는 같다"고 짚은 값은 host 자신의 식별자가 아니라 **호스트가 속한 클러스터 참조 객체의 `uuid`**(`clustermgmt.v4.config.ClusterReference.uuid`, 같은 클러스터 소속 호스트끼리 공유하는 게 정상)였음을 원본 덤프로 확인 — 코드에서 이 값은 전혀 안 쓰므로(호스트 키는 `ahv_host.extId`) 문제 없음을 설명. 덤프 중 하나를 잘못 읽어 "hostName 중복(phciap03)"으로 오인했던 것도 이후 원본 재확인으로 정정
- **Nutanix VM/호스트가 50개까지만 수집되던 문제 수정(1.0.33에 포함)**: "AWX 수집 시 VM이 50개밖에 안 된다"는 질문으로 조사, Nutanix v4 API가 `$page`(0-base)/`$limit`(기본값 낮음, 최대 100) 페이지네이션 대상이라는 걸 웹 문서로 확인. `push_nutanix_systems_instance_tasks.yml`에 `$limit=100`을 명시하고 1페이지 응답의 `metadata.totalAvailableResults`로 전체 개수를 계산해 남은 페이지를 마저 가져오도록 호스트/VM 둘 다 수정 — 페이지 수 계산식(`round(0,'ceil')`)은 독립적인 Jinja2 실행으로 250/100/50/0건 케이스를 시뮬레이션해 검증
- **배포 프로세스 특이사항**: 이번 세션에서 CMDB 이미지(1.0.32, 1.0.33)와 AWX 플레이북 파일이 서로 다른 반입 경로라는 걸 실제로 겪은 뒤, 사용자가 플레이북 파일도 별도로 반입하는 걸 인지 — CLAUDE.md에는 아직 이 구분이 명시돼 있지 않아 추후 필요시 문서화 검토 여지 있음
- **부수 정리**: dedup 로직 로컬 검증용으로 작성한 `test_dup_vm.py`가 `docker cp`로 컨테이너에 넣는 과정에서 docker-compose 볼륨 마운트를 통해 리포지토리 루트에 새어나온 걸 커밋 직전에 발견해 삭제(커밋 대상 아니었음)
- 1.0.32(필드명 수정), 1.0.33(중복 방어 + 페이지네이션) 순서로 각각 VERSION/CHANGELOG 갱신 → `docker build`/`save`/zip 압축 → 커밋 확인 → push → GitHub Release 생성까지 두 차례 진행, 오래된 릴리즈 첨부파일(최신 3개 제외) 정리도 매번 함께 수행
- **자산 상세 "연결된 시스템" 표 ORA-00932 수정(1.0.34)**: 시스템 push된 자산의 상세 화면을 열면 500 에러가 난다는 제보 — 파드 로그 트레이스백으로 `dashboard/queries.py`의 `get_system_hosts_for_vms()`를 지목. 목록 화면(`get_system_host_queryset`)은 이미 `.defer("extra", "source__raw_response")`가 있는데 이 함수만 빠져있던 걸 발견 — `annotate(Count(distinct=True))`가 `select_related("source")`로 끌려온 JSONField(NCLOB) 컬럼까지 GROUP BY에 포함시켜 발생한, CLAUDE.md에 이미 문서화된 패턴과 완전히 동일한 사례. 같은 defer 추가로 수정, 로컬에서 실제 SQL을 찍어 NCLOB 컬럼이 GROUP BY에서 빠졌는지 직접 확인
- **WAS 상세에 컨테이너별 Data Source 표 신규(1.0.34에 포함)**: "각 JEUS 컨테이너가 쓰는 data-source도 모달에 보여달라"는 요청 — `samples/jeus8/domain.xml`을 직접 열어 `<resources><data-source><database>`(도메인 레벨 정의)와 각 `<server>`의 `<data-sources><data-source>이름</data-source>` 참조 목록 구조를 확인. 하나의 데이터소스를 여러 컨테이너가 공유하는 게 일반적이라(같은 샘플에서 실제로 컨테이너 2개가 데이터소스 1개를 공유) WebToB의 SvrGroup↔VHost와 동일하게 M2M으로 설계 — 새 모델 `JeusDataSource`(`was/models.py`), 파서(`was/parsers.py`)에 도메인 레벨 데이터소스 파싱 + 컨테이너별 참조 목록 추출 추가, 동기화(`was/sync.py`)는 webtob 커넥터와 같은 통짜 재생성 패턴. 비밀번호는 암호화된 값이라도 저장하지 않기로 함(민감정보 최소 수집 원칙). `manage.py makemigrations`로 마이그레이션 생성, `samples/jeus8/domain.xml` 실제 재push로 DB 반영(데이터소스 1건이 컨테이너 2개에 정상 연결) + Playwright 스크린샷으로 화면까지 검증
- **로컬 앱 프리뷰**: "로컬에서 한번 보게 띄워달라"는 요청으로 `docker compose up` + 임시 계정(`claude_preview`, 기존 `admin` 계정 안 건드림)으로 로그인해 Playwright 스크린샷 전달 - 이후 WAS 상세 화면 검증에도 같은 방식 재사용
- **JEUS6 WAS 설정 파싱 신규 지원(1.0.35)**: "JEUS6도 파싱하고 싶다"는 요청 — 코딩 전 `samples/jeus6/`(`JEUSMain.xml` + `servlet_engine1`/`servlet_engine3`의 `WEBMain.xml`) 구조부터 직접 열어서 분석하고, 애매한 지점 4가지(멀티파일 payload를 문자열/dict 중 어떻게 묶을지, 데이터소스↔컨테이너 연결 파일에 참조가 없는데 어떻게 처리할지, 폴더명↔engine 번호 매칭 규칙이 항상 성립하는지, JEUSMain.xml 하나에 여러 노드가 담길 수 있는지)를 코딩 전에 먼저 질문으로 확인받음 — 전부 "구조화 dict로 payload 구성 / 노드의 모든 컨테이너에 데이터소스 전부 연결 / 폴더명 규칙 항상 성립 가정 / 1파일=1노드 가정"으로 결정
  - `was/parsers.py`에 `parse_jeus6(files: dict)` 신규 — **`parse_jeus`와 완전히 같은 반환 형태**를 맞춰서 `was/sync.py`(`sync_jeus`)를 kind 분기 없이 그대로 재사용(모델도 `JeusContainer`/`JeusWebtobConnector`/`JeusDataSource` 전부 공유). `<application>`의 `"{node명}_{container명}"` 합성 키 파싱, `servlet_engine{N}`이 컨테이너 이름이 아니라 `<engine-command><name>engine{N}</engine-command>`의 엔진 번호와 매칭되는 점, JEUS6 데이터소스는 `data-source-id`가 없어 `export-name`을 대신 쓰는 점, 컨테이너별 참조가 없어 그 노드의 모든 컨테이너에 일괄 연결하는 점을 반영
  - `WasConfigSource.Kind.JEUS6` 추가, `content`(단일 문자열) 대신 `files`(파일명→원본 텍스트 dict)를 받도록 `was/serializers.py`/`was/views.py` 확장(kind=jeus는 기존 그대로) — `raw_content`(TextField 하나)엔 파일 경계를 표시해 합친 텍스트를 저장하되 파싱은 항상 원본 dict로 함
  - 신규 플레이북 `awx/push_jeus6_config_to_cmdb.yml` — JEUS6은 admin 서버 개념이 없어 **노드 전부를 인벤토리 대상으로 실행**해야 한다는 점이 기존 `push_jeus_config_to_cmdb.yml`(admin 서버 한 대만)과 가장 큰 차이. `find`+`slurp`로 JEUSMain.xml과 모든 `servlet_engine*/WEBMain.xml`을 모아 `files` dict로 push
  - `samples/jeus6/` 실제 재push(테스트 자산 임시 생성)로 DB 반영 확인(컨테이너 2개, 각각 WebToB 커넥터 1개+데이터소스 6개 연결) + Playwright 스크린샷으로 화면까지 검증. CLAUDE.md의 "WAS 설정" 섹션도 "jeus6는 파서 미구현" 문구를 실제 구현 내용으로 갱신
- **JEUS6 한 호스트 다중 인스턴스(계정별) 지원(1.0.36)**: JEUS6 지원 배포 직후 "한 서버에 계정을 다르게 해서 JEUS6가 여러 개 뜨는 경우(예: ddorap01에 jeuscm/jeuslt)도 있다"는 제보 — 코딩 전 먼저 원인부터 짚음: `WasConfigSource`가 `(asset, kind)`로만 유일해서 두 번째 push가 첫 번째를 덮어씀, `<node><name>`(물리 호스트명)만으론 계정이 달라도 같은 값이라 설정 내용으로는 구분 불가능하다는 점을 설명하고 apache/nginx의 hostname 명시 패턴을 근거로 제시
  - 코딩 전 질문 3가지(식별값을 AWX가 명시적으로 보낼지/무슨 값을 쓸지/화면에 어떻게 보여줄지)를 확인받은 뒤 진행 — "AWX가 OS 계정명을 명시적으로 보내고, WAS 목록/상세에 인스턴스명 컬럼 추가"로 결정
  - `WasConfigSource.instance_name` 신규 필드 + 유니크 키를 `(asset, kind, instance_name)`로 확장(`kind=jeus`는 항상 빈 문자열이라 기존 동작 그대로 보존), `was/serializers.py`/`was/views.py`가 kind=jeus6일 때 이 값을 필수로 받아 그대로 저장. WAS 목록·JEUS 컨테이너 목록·엑셀 다운로드 2종·WAS 상세 전부 "인스턴스" 컬럼 추가(`dashboard/queries.py`/`views.py`/`list_export.py`/템플릿)
  - `awx/push_jeus6_config_to_cmdb.yml`에 `jeus6_instance_name`(필수) 변수 추가 - 같은 호스트를 계정별로 여러 번 push해야 한다는 점을 주석에 명시
  - 실제로 같은 샘플을 `instance_name=jeuscm`/`jeuslt`로 두 번 push해서 두 행이 서로 안 덮어쓰고 독립적으로 남는 것까지 직접 검증(마이그레이션 생성/적용, Playwright로 목록 화면 스크린샷)

## 2026-08-05

- **시스템 상세에 "원본 응답 보기" 추가**: "새 System host field definition 등록할 때 원문 API 응답값을 모달에서 못 봐서 dot-path 찾기 어렵다"는 지적 — 자산 상세의 `raw_facts_json`과 같은 패턴으로 `SystemHost.extra`를 `<details>` 접이식 박스에 JSON으로 노출(`SystemDetailView`/`system_detail.html`). `SystemHostFieldDefinition.key`/`kind_key_overrides`가 참조하는 게 소스 전체(`SystemSource.raw_response`)가 아니라 호스트별 `extra`라 그쪽을 노출하는 게 맞다고 판단.
- **베어메탈(물리) 장비 수기 등록 기능 신규**: "시스템 탭이 vCenter/Nutanix push로만 채워지는데 베어메탈은 어떻게 관리할지" 코딩 전 설계 논의부터 진행
  - 데이터 출처로 (a) 기존 facts push 재사용 (b) BMC/IPMI 신규 연동 (c) systems 전용 API로 별도 배치 push 세 방향을 검토했으나, "시스템을 facts와 분리한 전제 자체가 이미 push 경로가 따로 있다는 것"이라는 사용자 지적으로 (c)까지도 재고 → 최종적으로 자동 수집 자체를 포기하고 **대시보드에서 사람이 직접 SystemHost를 생성**하는 방식으로 결정
  - `SystemSource.Kind.PHYSICAL` 신규 추가(마이그레이션 `0004_alter_systemsource_kind`, choices 메타데이터뿐이라 DB 실질 변경 없음). 자산 미정 상태(asset=null)로 먼저 등록하는 것도 허용(발주/랙 설치만 된 장비 대응) — hostname을 나중에 입력하면 `SystemVm` 1건으로 자기 자신을 셀프 링크해서 기존 "떠있는 OS" 표/"연결된 시스템" 표/vm_count를 코드 수정 없이 그대로 재사용(`systems/sync.py`의 `sync_physical_host_asset`)
  - "시스템" 목록에 "+물리 장비 등록" 버튼 + kind=physical 행 전용 "관리"(편집/삭제) 컬럼, 등록/편집 공용 모달(소스/이름/자산 hostname datalist) 신설. vCenter/Nutanix 행은 여전히 push 전용으로 잠금(신규 엔드포인트가 kind=physical만 대상으로 하고 나머지는 404 처리하는 것까지 확인)
  - "소스도 사용자가 입력하게 해달라"는 후속 요청으로 소스 이름을 폼 입력으로 전환(전산실/그룹별 관리 가능), `get_or_create_physical_source(name)`으로 변경 — 호스트를 다른 소스로 옮길 때 연결된 `SystemVm.source`도 같이 맞추도록 기존에 빠져있던 부분까지 같이 수정
  - Django test client + 실제 Playwright(Chromium)로 등록/수정/삭제/자산 연결 전체 흐름 검증(임시 테스트 계정 생성 후 세션 종료 시 삭제, 기존 `admin` 계정은 건드리지 않음)
- **물리 장비의 AUTO 필드를 MANUAL과 같은 라벨로 편집 가능하게 확장**: "수기 등록한 애들은 속성(CPU/제조사 등 AUTO 필드)을 못 채운다"는 지적으로 원인 조사
  - 원인: `SystemHostFieldValue`는 AUTO/MANUAL 저장 구조가 같지만(AUTO는 push 시 `sync_host_fields()`가 미리 채움), 화면에서 클릭 가능하게 보여줄지는 `fd.source==MANUAL`에만 묶여 있어 AUTO 필드는 물리 호스트에서도 영원히 읽기 전용이었던 것으로 확인(실제 Playwright로 재현해 확정)
  - `host.source.kind=="physical"`인 행은 AUTO 필드도 `is_manual=True`로 취급하도록 `build_system_host_rows`/`SystemHostManualFieldUpdateView` 수정 — kind=physical은 push 자체가 없어 `sync_host_fields()`가 절대 안 돌기 때문에 사람이 입력한 값이 다음 push에 덮어써질 위험이 없다는 점을 근거로, 필드 정의/라벨을 vCenter·Nutanix와 그대로 공유(물리 전용 중복 필드 등록 불필요 — "라벨을 같게 쓰고 싶다"는 요청에 정확히 부합)
  - vCenter/Nutanix 행은 계속 읽기 전용(서버에서도 400)인지 함께 검증. 이어서 "엑셀 업로드도 되는지" 질문에 확인해보니 `systems/excel_import.py`가 별도 코드 경로라 안 풀려있던 것 발견 — `parse_system_host_workbook`/`apply_updates` 둘 다 같은 예외를 적용해 셀 편집과 엑셀 업로드가 일관되게 동작하도록 수정, 실제 워크북 파싱→적용 스크립트로 검증(물리 행은 반영, vCenter 행은 여전히 무시됨을 확인)
- **오라클(폐쇄망) 호환성 리뷰**: 이번 세션 변경 전체를 CLAUDE.md의 NCLOB 원칙 기준으로 점검 요청 — 신규 `.distinct()`/`order_by()`/집계가 JSONField(`SystemHost.extra` 등)를 건드리는 지점이 없음을 코드로 확인, `.first()`가 실제로 어떤 컬럼으로 정렬되는지도 Django 소스(`query.py`)를 직접 읽어 검증(정렬 미지정 시 pk로 폴백 확인)
  - 리뷰 중 **JSONField도 TextField와 동일하게 Oracle에서 NCLOB로 매핑된다**는 걸 Django Oracle 백엔드 소스(`data_types["JSONField"]="NCLOB"`)로 재확인 — CLAUDE.md의 "환경" 섹션과 관련 메모(`feedback_oracle_testing_awareness`)가 지금까지 TextField만 언급하던 걸 JSONField까지 포함하도록 갱신(사용자 요청)

## 2026-08-03

- **구성도 화면 500 에러(ORA-00932) 수정(1.0.24)**: 폐쇄망에 반입 후 구성도 화면을 누르면 500 에러가 난다는 제보 — 트레이스백 확인해 원인부터 분석
  - `build_service_topology_graph`의 `JeusWebtobConnector` 조회가 `select_related("container")`로 `JeusContainer.deployed_apps_summary`(TextField→Oracle NCLOB)를 SELECT 컬럼에 끌어온 채 `.distinct()`를 걸어서 발생 — 코드 확인 결과 루프에서 `connector.container_id`만 쓰고 `connector.container`는 참조하지 않아 `select_related("container")` 자체가 애초에 불필요했던 것 확인, 제거
  - 이 사례를 계기로 CLAUDE.md에 "로컬(Postgres) 통과 ≠ Oracle에서도 안전"을 명시적으로 추가 — DB 쿼리 변경 시 TextField/NCLOB 위험을 코드 레벨로 재점검하는 걸 검증 절차에 포함시키기로 함(사용자 요청)
- **서비스 탭 UI 개선(1.0.25)**: "서비스명 셀 안에 구성도 링크가 같이 있어서 클릭 영역이 헷갈린다"는 지적으로 코딩 전 검토
  - "구성도" 텍스트 링크를 서비스명 왼쪽 별도 버튼 컬럼(`is-light is-small`)으로 분리 — 인라인 편집 클릭 영역과 페이지 이동 액션을 분리
  - 이어서 "Hostname/솔루션도 클릭하면 상세 모달 뜨게 해달라"는 요청으로, 웹설정/WAS 목록 화면이 이미 쓰던 행 클릭→AJAX fetch→모달 패턴을 셀 단위로 재사용해 자산 상세/WEB 설정 상세/WAS 설정 상세 모달 추가
- **구성도 기능 확장(1.0.26 → 최종 1.0.27로 통합 릴리즈)**: "구성도 그림 안에서도 클릭하면 모달 뜨게 가능할지" 검토 요청
  - Graphviz의 `URL` 속성(노드/클러스터에 지정하면 SVG 출력에서 해당 도형이 `<a>`로 감싸짐)을 실제로 테스트해 확인 후, WEB/WAS 박스·OS 박스·System 박스 전부 같은 fetch+모달 패턴으로 클릭 가능하게 구현(URL 경로 패턴으로 어떤 상세인지 판별)
  - "OS 박스에 'OS' 대신 종류(AIX/RHEL 등), Hostname 옆에 IP도 보여달라"는 요청으로 `asset.hostfact.os_family`/`asset.primary_ip` 반영
  - "구성도 크기 조절이 화면에서 가능한지" 검토 → SVG는 벡터라 화질 저하 없이 가능하다고 판단, 저시력 사용자 고려해 마우스 휠 대신 `−`/`기본값`/`+` 버튼으로 구현(버튼 텍스트도 "100%" 대신 "기본값" 고정 문자열로 사용자 요청에 따라 수정)
  - **주의**: 이 작업(1.0.26)은 빌드까지 해두고 커밋 확인을 받기 전에 다음 요청(WAS kind 재정리)으로 넘어가 실제로 커밋/릴리즈되지 않았음 — 이후 1.0.27에 합쳐서 릴리즈
- **WAS `kind` 재정리: `jeus8` → `jeus`(1.0.27)**: "JEUS6/7/8/9 지원을 고민 중인데 kind를 어떻게 나눌지" 검토 요청
  - domain.xml 레이아웃이 같은 JEUS 7/8/8.5/9는 `kind=jeus` 하나로 묶고, 파일 구조가 완전히 다른 JEUS 6는 향후 `kind=jeus6`로 분리하기로 결정 — kind 문자열에 버전이 일부 겹치는 것(jeus6/jeus)은 kind가 파서 선택용 키이고 실제 세부 버전은 `solution_version`이 따로 담당해 역할이 안 겹친다고 판단해 문제 삼지 않음
  - 기존 `kind=jeus8` 데이터를 마이그레이션으로 일괄 전환, 관련 URL/AWX 플레이북(파일명 `push_jeus8_config_to_cmdb.yml`→`push_jeus_config_to_cmdb.yml`)/화면 라벨 전부 개명 — 폐쇄망 반입 시 AWX Job Template의 플레이북 경로 갱신 필요함을 안내
  - 샘플(`samples/jeus8/domain.xml`) 재push로 기능 검증 + `sqlmigrate`로 choices 변경이 실제 DB에 no-op임을 확인해 Oracle 안전성 재확인
- **WAS/WEB kind 표시 라벨 단순화(1.0.28)**: "JEUS 7+" 대신 "JEUS"로(jeus6만 구분되면 충분), "WebtoB" 대신 "WEBTOB"(대문자)로 요청 — 구성도의 WEB 노드 라벨도 하드코딩 문자열 대신 `source.get_kind_display()`로 통일해서 이후 라벨이 또 바뀌어도 모델 한 곳만 고치면 되게 정리
- **AUTO 필드 dot-path 리스트 인덱스 지원(1.0.29)**: "Windows MAC 주소를 facts 컬럼에 추가했는데 표시가 안 된다"는 제보 — raw facts 확인해보니 Windows는 Linux의 `default_ipv4`(dict) 같은 평평한 경로가 없고 MAC이 `interfaces`라는 **리스트** 안에만 있어서, `extract_json_path`가 리스트를 만나면 무조건 `None`을 반환하는 기존 문서화된 한계에 걸린 것으로 확인
  - `extract_json_path`(`facts/dynamic_fields.py`)에 숫자 인덱스 세그먼트 지원 추가(`interfaces.0.macaddress`) — 조건 필터링/전체 순회는 여전히 미지원("필드 하나=값 하나" 원칙 유지), `systems` 앱도 같은 순수 함수를 재사용하고 있어 vCenter/Nutanix 쪽에도 자동으로 적용됨
  - `samples/awx/windows.json`(사용자가 준비해둔 미커밋 샘플) 재push로 검증 — 이 파일에 최상위 `hostname` 키가 없어 API 직접 호출 시 안 먹히는 것도 함께 확인, 사용자에게 안내
  - 실제 운영 환경의 `FactFieldDefinition`(MAC 주소, `os_family_key_overrides`)은 admin 데이터라 코드로 못 고침 — `{"Windows": "ansible_facts.interfaces.0.macaddress"}`로 직접 수정 후 소급 백필하도록 안내
- **서비스 탭 저장 시 ORA-00932 추가 발견 및 수정(1.0.29에 포함)**: "서비스명 수정/등록하려고 하면 오류난다"는 제보 스크린샷으로 확인
  - `was/linkage.py`의 `get_connected_containers`(WebToB↔JEUS 서비스 전파용)가 `JeusContainer.objects.filter(...).distinct()`를 쓰는데 `JeusContainer.deployed_apps_summary`(TextField→NCLOB)가 SELECT에 포함돼 발생 — 이번엔 SvrGroup-vhost M2M 조인 때문에 `.distinct()` 자체는 필요해서 `defer("deployed_apps_summary")`로 그 컬럼만 제외
  - 로컬에서 `apply_vhost_service()` 직접 호출해 정상 동작 확인(Postgres라 NCLOB 에러 자체는 재현 안 됨 — 코드 검토로 원인 확정)

## 2026-07-31

- **Windows 자산 OS/IP 필드 오적재 수정(1.0.18)**: `samples/awx/windows.json`(실제 Windows facts 샘플)을 대시보드에서 확인해보니 OS 컬럼에 "Microsoft Windows Server 2022 Standard"(풀네임)가 찍히고 os_version은 커널 빌드번호("10.0.20348.0"), IP는 빈 값으로 나오는 문제 발견 — 코딩 전 원인 검토부터 진행
  - `HostFact.os_family`가 `ansible_facts.distribution`을 그대로 썼는데, 리눅스는 이 값이 우연히 family와 같아(`RedHat`) 안 드러났을 뿐 윈도우는 풀네임이라 어긋남 — ansible 표준 `os_family` 키로 교체
  - `os_version`은 윈도우의 `distribution_version`이 사람이 읽는 버전이 아니라 커널 빌드번호라, `os_family=="Windows"`일 때만 `distribution`(마케팅명)을 쓰도록 분기 — `facts/views.py`/`facts/approval.py` 두 곳에 따로 있던 추출 경로 정의를 `facts/approval.py`의 `FIXED_FIELD_EXTRACTORS`/`compute_fixed_values()` 한 곳으로 통합(승인 diff와 실제 반영이 어긋날 위험 제거)
  - `Asset.primary_ip`는 윈도우 facts에 아예 없는 `default_ipv4`에만 의존하던 걸, 없으면 `interfaces[].default_gateway`가 걸린 인터페이스의 `ipv4.address`로 폴백하도록 수정
  - 이어서 "대시보드에 실제 보이는 os_version 컬럼"이 방금 고친 `HostFact.os_version`이 아니라 완전히 별개의 AUTO 동적 필드(`ansible_facts.distribution_version`)라는 걸 재확인 과정에서 발견 — AUTO는 dot-path 하나만 지원해 OS별 분기가 안 되는 구조적 한계 확인
  - "리눅스 종류(RHEL 외)/AIX도 늘어날 텐데 화면 구성을 어떻게 할지" 고민에 대해서는, ansible의 `os_family`가 이미 RHEL/CentOS/Rocky 등을 "RedHat"으로, Ubuntu/Debian을 "Debian"으로 묶어주므로 화면 구조 변경은 불필요하다고 판단 — 다만 필드 값 자체가 OS별로 다른 raw facts 키에서 와야 하는 경우가 있어 `FactFieldDefinition.os_family_key_overrides`(JSON) 신규: os_family별로 다른 경로가 필요한 필드만 override를 채우고, 값이 같은 OS는 기존 `key`를 그대로 씀. 사용자 요청으로 admin help_text에 override 1개/2개 이상 예시 둘 다 명시
  - "OS 목록의 고정 컬럼이 Hostname/IP만이어야 하는지" 재확인 요청에는 실제로 코드를 확인해 "OS(os_family)도 고정 컬럼이 맞다"고 사용자가 최종 확인 — 변경 없이 유지
  - 실제 push(`/api/facts/`)와 백필(`backfill_field`) 둘 다로 Windows(`iawxap01`)/Linux(`drnrap01`) 검증, `manage.py check` 통과 확인 후 릴리즈
- **대시보드 hostname 대문자 표시**: "hostname에 들어가는 영문은 대시보드 종류 구분 없이 대문자로 보이게" 요청 — 저장값(소문자 정규화)은 그대로 두고 표시만 바꿔야 검색/API 매칭이 안 깨진다고 판단해 CSS(`dash-hostname` 공용 클래스, `text-transform: uppercase`)로 처리, `base.html`에 한 번만 정의
  - hostname이 나오는 화면 18개(자산/WEB/WAS 목록·상세·변경이력, vhost 목록 3종, 서비스 조회, 어플리케이션, 엑셀 업로드 결과) 전수 확인 후 적용 — vhost 자체의 `hostname`(도메인) 필드는 별개 개념이라 제외
  - CSS가 안 먹는 `<title>`(브라우저 탭)은 `|upper` 필터, JS로 모달 제목을 조립하는 곳(`asset_list.html`)은 `.toUpperCase()`로 별도 처리
  - Playwright로 실제 로그인 세션 쿠키를 주입해 OS 목록/상세 화면 스크린샷까지 찍어서 시각 확인
- **검색 규칙 확장**: "OS 목록도 os_family로 검색되게" 요청으로 `dashboard/queries.py`의 자산 검색 조건에 `hostfact__os_family__icontains` 추가(1:1 관계라 기존 `.distinct()` 로직에 영향 없음). 이어서 "WEB/WAS도 종류로 검색되게" 요청에 `_kind_search_q()` 공용 헬퍼 신설 — `kind` 원시값(webtob/apache/nginx/jeus8)뿐 아니라 표시 라벨("JEUS 8"처럼 원시값과 다른 경우)도 매칭되게 처리, 두 목록 화면 검색창 placeholder도 갱신. 실제 검색 결과로 각각 검증(회귀 없음)
- **AIX Python 버전 이슈 검토(코드 변경 없음)**: AWX facts 수집 시 AIX가 Python 3.7까지만 공식 지원한다는 제약 관련 논의 — 실제로는 AIX Toolbox에 3.9 패키지가 있어 완전히 막힌 건 아니라는 점, `ansible_python_interpreter` 경로 지정 패턴(`awx/OS_SPECS.md`에 이미 있는 관례), 툴박스 rpm 수동 설치 시 흔한 의존성 누락(openssl/xz-libs/ncurses) 등을 조사해 공유. 사용자가 "아직 검토 단계"라고 해서 문서 반영은 보류 — 실제로 테스트해보면 `OS_SPECS.md`에 결과 기록 예정
- **자산 엑셀 다운로드 IP/OS 컬럼 누락 수정(1.0.20)**: "OS 목록 엑셀 추출 시 Hostname만 보이고 IP/OS가 빠진다"는 제보 — 확인해보니 `export_manual_field_workbook`(`dashboard/excel_import.py`)이 `hostname`+동적 필드(`FactFieldDefinition`)만 내보내게 짜여 있었고, IP(`primary_ip`)/OS(`os_family`)는 `LEADING_FIXED_COLUMNS`(대시보드 화면 전용 하드코딩 컬럼)라 원래부터 이 함수가 모르는 값이었음(신규 버그 아님)
  - 그냥 컬럼만 추가하면 업로드 파서가 "모르는 컬럼"으로 걸어 파일 전체를 에러 처리하는 문제가 있어, AUTO 필드와 같은 패턴(참고용으로 싣되 업로드 시 항상 무시)으로 `FIXED_REFERENCE_LABELS`(`["IP", "OS"]`) 추가해 헤더 매칭에서 자동으로 스킵되게 처리
  - 다운로드 헤더/값 확인 + 그대로 재업로드해서 에러 없이 반영 0건으로 통과하는 것까지 검증
- **"구성도"(WEB↔WAS↔시스템 연결 시각화) 신규(1.0.23)**: "OS와 WEB/WAS/시스템이 매핑되는 인프라 구성도를 자동으로 그려서 서비스 단위로 보고 싶다"는 아이디어로 시작, 코딩 전 검토부터 여러 차례 진행
  - **전제 작업 — 서비스명을 `core.Service` FK로 전환**: 지금까지 `service_name`이 `WebtobVhost`/`ApacheVhost`/`NginxVhost`/`JeusContainer`에 각자 자유 텍스트로 있어서, WebToB↔JEUS처럼 실제로 연결된 것끼리도 오타로 서비스명이 어긋날 수 있다는 문제를 먼저 해결. 새 `Service` 모델(`core` 앱) 도입 + 데이터 마이그레이션으로 기존 값 이관(같은 이름 문자열은 하나의 Service로 합침). 부수적으로 서비스 조회 화면에서 Apache/Nginx 서비스명 수정이 원본 vhost에 반영 안 되던 잠재 버그도 같이 수정
  - **편집 창구를 "서비스" 탭 하나로 통합**: 도메인 기준 WEB 표(기존 `WebServiceDomain`)와 컨테이너 기준 WAS 표(신규)를 한 페이지에 배치하고 여기서만 편집, WebToB/Apache/Nginx vhost 목록·JEUS8 컨테이너 목록·상세 모달의 인라인 편집(연필 아이콘)은 전부 제거해 읽기 전용으로 전환 — 더 이상 안 쓰는 `*ServiceUpdateView` 4개와 관련 URL/모달/JS도 완전 삭제
  - **WebToB↔JEUS 연결 전파**: 실제로 연결된 vhost/컨테이너는 한쪽만 고쳐도 반대쪽까지 즉시 같이 맞춰지게(`was/linkage.py`) — 연결된 쪽에 이미 다른 서비스명이 있으면 사용자가 "다르면 경고 후 확인 받기" 방식을 선택해서, 저장 전 확인창을 띄우고 동의하면 `force=1`로 덮어씀
  - **구성도 시안 검토**: 처음엔 표/레인 방식(WEB vhost-WAS 컨테이너 한 쌍 = 한 줄)으로 구현했는데, 사용자가 "실제로 그림(System 위에 OS, OS 위에 WEB/WAS가 쌓이고 화살표로 호출 방향 표시)을 원한다"고 명확히 해서 재검토 → 박스 스택 목업을 만들어 보여줬으나 "OS가 이중화되면 이 방식으로는 애매하다, 오픈소스 그래프 라이브러리도 검토해달라"는 피드백을 받음
  - 실제로 Docker 컨테이너에 graphviz를 임시 설치해 WebToB 2대×JEUS 2대(2×2 이중화, 커넥터 4개) 시나리오를 Graphviz/Mermaid/표 세 가지로 렌더링해 비교하는 아티팩트를 만들어 제시 — 사용자가 Graphviz안 선택
  - **최종 구현**: `dashboard/topology.py` 신규 — 레인이 아니라 진짜 그래프(노드+엣지)로 데이터를 만들어서, 같은 물리 서버(asset)를 가리키는 노드는 렌더링 단계에서 자동으로 같은 OS 박스에 합쳐지게 설계(이중화 문제의 근본 해결). `subprocess`로 `dot -Tsvg` 실행해 서버에서 SVG를 그려 내려줌(클라이언트 JS 불필요). `Dockerfile`에 `apt-get install graphviz` 추가(이 프로젝트 최초의 apt 설치) — 로컬 이미지 재빌드해서 실제 앱 안에서 렌더링까지 확인
  - 이어서 "도메인/포트 정보가 안 보인다, TLS면 https/아니면 http를 붙여달라"는 요청으로 WEB vhost 노드 라벨에 `프로토콜://도메인:포트` 추가(`ssl_flag` 기준 프로토콜 결정)
  - **"서비스 위에 더 상위 그룹 개념도 있어야 할 것 같다"는 아이디어 논의**: `core.ServiceGroup` + `Service.group` FK로 구조적으로는 어렵지 않다고 확인. 다만 "그룹을 조회/필터용 라벨로만 쓸지, 구성도에서 여러 서비스를 한 그림에 합쳐서 그리는 것까지 포함할지"가 구현 난이도를 크게 가르는 갈림길이라고 짚어줌 — 사용자가 후자까지 염두에 둔 아이디어라고 확인했으나 지금은 아이디어 단계로 보류, 구현 착수 안 함
  - 1.0.23으로 릴리즈(VERSION/CHANGELOG/Docker 이미지 빌드/GitHub Release, graphviz 포함된 이미지에서 `dot` 정상 동작 확인 후 배포)

## 2026-07-30

- **WebToB vhost의 Logging/ErrorLog가 실제 경로를 보여주도록 수정**: 웹 목록 모달에서 이 두 값이 `*LOGGING`절 엔트리 이름(`log1`, `log2`처럼)만 보여서 알아보기 어렵다는 지적. 코딩 전 검토 → `parse_webtob`이 이미 모든 절을 범용 파싱해서 `*LOGGING`절 데이터(FileName 포함) 자체는 파싱 결과에 있지만 `sync_webtob`이 이름값만 그대로 저장하고 있었던 게 원인
  - `sync_webtob`에 `_resolve_log_path` 추가 — `*LOGGING`절에서 이름→FileName 맵을 만들어 VHost 저장 시 resolve, 못 찾거나 FileName이 비어있으면 원래 이름값으로 폴백(완전히 비우지 않음)
  - 부수적으로 `WebtobVhost.logging`/`errorlog`의 `max_length`를 100→255로 확장(짧은 엔트리 이름 기준이던 걸 실제 경로 길이에 맞춤, Apache/Nginx와 통일) — 마이그레이션 하나 추가
  - 실제 `samples/webtob/APCS01_http.m` 재push로 `vhost1`의 값이 `log1`/`log2`에서 실제 경로로 바뀌는 것, 목록/상세 모달 렌더링까지 확인
- **엑셀 다운로드 없는 화면 10개에 추가**: 처음엔 "컬럼별 엑셀 필터"(엑셀처럼 헤더 클릭 → 체크박스로 값 필터링) 요청이었으나 검토 중 사용자가 방향을 바꿔 "그냥 화면마다 엑셀 다운로드만 있으면 될 것 같다"로 스코프 축소 — 필터 UI는 컬럼마다 카디널리티가 너무 달라서(hostname처럼 사실상 전부 다른 값 vs OS/종류처럼 몇 개 안 되는 값) 화면별로 설계가 갈리는 문제를 짚어준 게 결정에 영향
  - 변경 이력/WEB 목록·변경 이력/WebToB·Apache·Nginx vhost 목록/WAS 목록·변경 이력/JEUS8 컨테이너 목록/어플리케이션 — 총 10개 화면에 다운로드 버튼 신규(`dashboard/list_export.py`)
  - 기존 두 다운로드(자산 MANUAL 필드, 서비스 조회)와 같은 관례: 검색 필터 무시하고 항상 전체 데이터. 화면별 `get_*_queryset(request)`를 빈 GET 가짜 request로 그대로 재사용해서 Oracle NCLOB 대응 로직을 중복시키지 않음
  - tz-aware datetime을 openpyxl이 거부하는 문제(Excel이 타임존 미지원)를 로컬시간 변환 후 naive화해서 해결, Decimal도 float로 변환
- **자산 엑셀 다운로드/업로드에 AUTO 필드도 포함**: 위 작업 논의 중 "OS 목록은 컬럼이 admin에서 자유롭게 늘어나는데 그것도 엑셀 다운로드 되냐"는 질문에서 시작 — 확인해보니 기존 자산 엑셀(`export_manual_field_workbook`)은 MANUAL 필드만 대상이라 AUTO 필드는 화면엔 보여도 다운로드엔 안 실렸던 것. "다운로드엔 AUTO도 같이 싣고, 업로드할 땐 그 컬럼이 껴있어도 에러 안 나게" 요청
  - `_dynamic_fields_by_label`로 헤더 매칭 대상을 AUTO+MANUAL 전체로 넓히되(라벨 중복 검사도 전체로), 실제 반영(`PendingUpdate` 생성)은 여전히 MANUAL 필드만 — AUTO 컬럼 값을 고쳐서 올려도 조용히 무시(다음 push 때 어차피 덮어써지므로)
  - 다운로드 → 그대로 재업로드(에러 없음, 반영 0건) / AUTO 셀만 수정 후 업로드(무시됨) / MANUAL 셀 수정 후 업로드(반영됨) / 진짜 모르는 헤더(에러) 네 가지 케이스 전부 재현 검증
- **WAS(JEUS8) "배포된 앱" 표시를 path+id로 변경**: `context-path`가 실제 domain.xml 샘플에서 거의 다 `/`(URL 루트)로만 찍혀 있어 앱을 구분하는 데 도움이 안 된다는 지적 — 실제 구분되는 값은 `<path>`(배포 경로, 예: `/deploy/cmp`)라 이걸 `id`와 함께 보여주도록 `was/parsers.py` 수정. `samples/jeus8/domain.xml` 재push로 확인
- **Apache/Nginx에 SSL Protocols/Ciphers 추가**: WebToB에는 이미 있는데 Apache/Nginx엔 빠져있다는 지적으로 추가
  - Apache 샘플(`httpd-ssl.conf`)은 `SSLProtocol`/`SSLCipherSuite`를 `<VirtualHost>` 안이 아니라 파일 전역(mod_ssl 공통 설정)에 한 번만 두는 구조라, vhost 안에 값이 없으면 전역값으로 폴백하는 로직이 필요했음(`_parse_global_ssl_defaults`, `<VirtualHost>` 블록을 통째로 지워서 전역 영역만 스캔). Nginx도 `http{}` 최상위에 한 번만 두는 경우를 대비해 같은 폴백을 넣음(SSL 안 쓰는 vhost엔 채우지 않음)
  - `ApacheVhost`/`NginxVhost`에 `ssl_protocols`(CharField)/`ssl_ciphers`(TextField) 신규, 목록/상세 모달/엑셀 다운로드까지 반영
  - 정렬 컬럼 설계 중 `ssl_ciphers`가 TextField(Oracle NCLOB)라 정렬 대상이 되면 위험하다는 걸 미리 인지해서 애초에 정렬 목록에서 뺌(SSL Protocols는 CharField라 정렬 넣음) — 이 과정에서 **기존 WebToB의 "SSL RequiredCiphers" 컬럼이 이미 같은 이유로 정렬 가능하게 돼있던 걸(`ssl__required_ciphers`) 발견**, 사용자 확인 받아 같이 제거(잠재 버그였는데 로컬 Postgres에선 재현이 안 돼 지금까지 안 걸렸을 것)
  - `samples/apache/httpd-ssl.conf`/`samples/nginx/nginx.conf` 재push로 전역 폴백/서버별 값 둘 다 확인, 목록/상세/엑셀까지 검증
- **자산 상세를 모달 대신 실제 페이지로 신규**: "OS 목록은 컬럼이 admin에서 자유롭게 늘어나는데, 늘어나면 가로 스크롤이 보기 어려워질 것 같다"는 문제 제기로 코딩 전 검토부터 진행
  - 메인 테이블이 이미 쓰는 `build_rows()`를 재사용해 같은 컬럼(동적 필드 포함)을 세로 label-value 표로 보여주는 방식으로 결정 — admin에서 컬럼이 늘어도 코드 수정 없이 그대로 따라감
  - 구조는 webconfig/was 상세 화면과 동일한 패턴 채택: `/dashboard/assets/<pk>/` 진짜 상세 페이지(`base.html` extends) 신규, 목록 행 클릭 시 AJAX로 fetch해 모달에 주입(`DOMParser`로 특정 div만 추출) — process/webconfig 목록이 이미 쓰던 패턴 그대로 재사용. 기존 raw facts 전용 JSON 엔드포인트(`/facts/`)는 폐기하고 이 페이지 안에 `<details>`로 접어서 유지
  - MANUAL 필드는 이 화면에서 읽기 전용으로 결정(✎ 아이콘도 안 붙임) — 편집을 넣으려면 전용 모달을 또 띄워야 해서 "모달 안에 모달" 중첩이 되고, CLAUDE.md의 기존 관례(중첩 회피용 `prompt()`)로는 checkbox/select/date 타입까지 있는 MANUAL 필드를 못 다뤄서 스코프 밖으로 뺌
  - hostfact가 아직 없는 자산(facts 미수집)도 에러 없이 빈 값으로 처리되는 것까지 확인
- **통합대시보드 신규**: "상단 CMDB 로고를 누르면 통합뷰로 가게 하고, 자산별 카운팅을 한눈에 보여주고 싶다(예: OS 전체 몇 개, 리눅스/AIX 몇 개)"는 요청으로 시작, 코딩 전 검토부터 진행
  - 시안 논의: dataviz/artifact-design 스킬로 실제 클릭 가능한 아티팩트 목업 3개(숫자+막대 목록/스탯 타일 그리드/도넛+범례) 제작해 비교 → 사용자가 스탯 타일 그리드(B) 선택
  - 이어서 "타일 클릭하면 그 OS의 버전별 개수를 C안(도넛) 형태로 보여줄 수 있냐"는 요청 → 같은 아티팩트에 클릭 인터랙션(캔버스 도넛, 툴팁, 열림/닫힘 토글) 추가해서 먼저 시연
  - 실제 구현 직전 "os_version 컬럼을 추가해놔야 하지 않냐"는 질문에 확인해보니 `HostFact.os_version`은 이미 모델/수집 로직 다 있고 데이터도 들어와 있었음(화면에 노출만 안 됐던 것) — 착오였음을 설명하고 노출만 추가하는 걸로 진행
  - "OS만 만들었는데 WEB/WAS도 같은 형태로 추가 가능하냐"는 후속 요청에 검토: `WebConfigSource`/`WasConfigSource`의 `kind`/`solution_version`이 OS의 `os_family`/`os_version`과 완전히 같은 구조(둘 다 CharField)라 그대로 재사용 가능하다고 확인. "전체" 기준(서버 수 vs vhost 수)과 WAS의 kind 단계 유지 여부를 사용자에게 확인받고(각각 서버 수, 확장성 위해 유지) 구현
  - 구현은 처음부터 OS 하나로 짜지 않고 `_build_category_tiles`/`_breakdown_by_field` 공통 헬퍼 + `sections` 리스트 기반으로 일반화 — 섹션이 늘어나도 뷰에 한 줄만 추가하면 되는 구조. 이름은 "통합뷰"로 시작했다가 사용자 요청으로 "통합대시보드"로 일괄 변경
  - `/dashboard/`(루트)가 원래 연결된 화면이 없어 404였는데 이 화면을 그 자리에 배치해 자연스럽게 해결
  - 실제 DB 데이터로 OS/WEB/WAS 세 섹션 타일·퍼센트·드릴다운 도넛(RedHat 9.4, Apache 버전, WebToB "버전 미상" 묶음 등)까지 전부 확인
- **1.0.17 릴리즈 전 Oracle/폐쇄망 호환성 검토**: 위 통합대시보드가 처음 만드는 집계(GROUP BY) 화면이라 반입 전 점검 요청
  - 새로 추가한 집계는 전부 `CharField`(os_family/os_version/kind/solution_version)만 대상이라 `TextField`→NCLOB 문제 없음을 확인, `.distinct()`도 새로 추가한 데 없음(전부 `.values().annotate(count=...)` 단순 집계)을 코드 전수 확인
  - 새 마이그레이션 2개(WebtobVhost max_length 변경, ApacheVhost/NginxVhost SSL 필드 추가) 전부 표준 Django 오퍼레이션이라 Oracle에서도 동일 동작
  - `openpyxl`은 기존 의존성 재사용(신규 패키지 없음), 이미지 빌드도 `--no-index --find-links=vendor/wheels`로 인터넷 없이 정상 완료되는 것 확인
  - 이미지 버전 관리 절차대로 1.0.17 빌드·릴리즈 진행

## 2026-07-29

- **Apache/Nginx 웹설정 파싱 추가**: `samples/apache/httpd-ssl.conf`, `samples/nginx/nginx.conf` 샘플을 받아 WebToB와 같은 방식으로 파싱해 대시보드에 노출, 도메인/포트 기준으로 서비스 조회(`WebServiceDomain`)에도 연계. 코딩 전에 검토부터 진행(Plan 모드) — 세 가지 확인 필요 사항을 사용자에게 질문:
  - vhost 단위 전용 목록은 WebToB처럼 kind별로 화면을 분리 유지하기로 결정(공통 컬럼 통합 화면은 이미 있는 `/dashboard/webconfig/`가 그 역할) — CLAUDE.md에 "나중에 nginx/apache가 붙어도 이 화면을 공유하지 않는다"고 미리 못박아둔 문구와 상충되지 않게 확인 후 진행
  - 자산(hostname) 판별: 설정 파일 안에 서버 자신을 가리키는 절이 없어(WebToB의 `*NODE`와 달리) AWX가 `inventory_hostname`을 payload에 별도 필드로 전송하는 방식으로 결정(facts push와 동일 패턴)
  - ProxyPass/proxy_pass 대상은 WebToB의 SvrGroup/Server/Uri 같은 관계형 모델링 없이 vhost에 요약 문자열 컬럼(`proxy_summary`) 하나로 결정
  - `ApacheVhost`/`NginxVhost` 모델 신규(필드명을 `WebtobVhost`와 맞춰 `sync_service_domains()`를 수정 없이 재사용). `parse_apache`(정규식 기반 `<VirtualHost>` 블록 추출)/`parse_nginx`(중괄호 깊이 추적 토크나이저로 `server {}` 블록 추출, 주석 안에 있는 `{`/`}`가 블록 경계를 깨는 문제가 있어 파싱 전 라인 단위 주석 제거를 먼저 적용해 해결) 신규 파서, `sync_apache`/`sync_nginx`는 이름(`hostname:port` 합성)으로 upsert해 수기 입력한 서비스명 보존
  - Ingest API(`WebConfigIngestSerializer`)에 `hostname` 필드 추가, `awx/push_apache_config_to_cmdb.yml`/`push_nginx_config_to_cmdb.yml` 신규(설정 파일 slurp + `inventory_hostname` 전송)
  - 공통 목록(`/dashboard/webconfig/`)의 `vhost_count`가 `WebtobVhost`의 `related_name="vhosts"` Count 하나에만 의존해서 apache/nginx 소스는 항상 0으로 나오는 걸 미리 발견 — 세 kind의 Count(distinct)를 더하는 방식으로 수정, 검색 필터도 세 kind 모두 포함하도록 확장
  - Apache/Nginx 전용 vhost 목록 화면(`/dashboard/webconfig/apache/vhosts/`, `/dashboard/webconfig/nginx/vhosts/`) 신규 — WebToB 화면과 동일 골격(전용 모달 서비스명 편집, sticky 컬럼)
  - 로컬 Docker Compose에서 실제 push(샘플 파일 그대로) → vhost 파싱(Apache 11개/Nginx 7개) → `WebServiceDomain` 연계 → 대시보드 목록/상세/검색/정렬/서비스명 인라인 편집 → 재push 시 서비스명 보존 → 엑셀 export/import 반영까지 end-to-end 검증
- **솔루션 버전 AUTO 추출을 Apache/Nginx까지 확장**: WebToB처럼 이 둘도 설정 파일 안에 버전 정보가 없어 명령어(`apachectl -version`/`nginx -v`)로만 확인 가능하다는 사용자 지적으로 추가 구현
  - `webconfig/version_extract.py`에 `extract_apache_version`/`extract_nginx_version` 추가 — 기존 `# CMDB_SOLUTION_VERSION:` 마커 방식 재사용, Apache/Nginx는 Fix 개념이 없어 버전만 채우고 Fix는 항상 빈 문자열
  - Apache는 `apachectl -version` 출력이 "Server version"/"Server built" 두 줄인데 두 번째 줄(빌드 날짜)은 안 쓰므로 플레이북이 첫 줄만 마커에 담아 전송 — 마커를 한 줄로 유지해 1.0.13에서 겪은 "마커와 다음 내용 사이 개행이 리터럴 `\n`으로 깨지는" 문제를 원천적으로 피함
  - Nginx는 버전을 stdout이 아니라 stderr로 출력하는 게 기본 동작이라 플레이북이 `stderr_lines`를 우선 확인하고 없으면 `stdout_lines`로 폴백
  - 마커를 얹은 상태로 실제 push해 `solution_version`이 정확히 채워지고 vhost 파싱/서비스명 보존에 영향 없는 것까지 검증
- **Oracle NCLOB `.distinct()` 문제 재발 방지 검토**: 사용자가 "기존에 폐쇄망 반입해서 에러난 경우가 있었다"며 위 신규 기능의 폐쇄망 안전성 검토 요청
  - 검토 결과 신규 코드에 동일 클래스 버그 발견: `get_apache_vhost_queryset`/`get_nginx_vhost_queryset`가 검색 시 `.distinct()`를 거는데 `proxy_summary`(`TextField`→Oracle NCLOB)가 걸려있어 `ORA-00932` 가능성 — 로컬은 Postgres라 재현 안 돼 사전 검증에서 못 잡았음
  - 부수적으로 기존 코드의 미해결 동일 버그도 발견: `get_webtob_vhost_queryset`이 `select_related("ssl")`로 끌고 오는 `WebtobSsl.required_ciphers`(`TextField`)도 검색 시 `.distinct()`에 걸림 — 1.0.12에서 `raw_content`/`extra_sections`는 고쳤지만 이 필드는 놓쳤던 것(`WORKLOG.md`의 1.0.12 "발견했지만 보류" 항목과 연결되는 문제)
  - 세 쿼리 모두 검색 필터가 own 필드/forward FK만 참조해 to-many 조인이 없다는 걸 확인 — 애초에 중복 행이 생길 수 없는 구조라 `defer()` 대신 불필요한 `.distinct()`를 제거하는 방식으로 수정(목록에 `proxy_summary`를 그대로 노출해야 해서 defer는 N+1을 유발하므로 이쪽이 더 나음). 쿼리셋의 `.query`를 직접 찍어 `DISTINCT`가 빠졌는지, 정말 필요한 `get_webconfig_queryset`(to-many 조인 있어 유지)엔 NCLOB 컬럼이 안 걸리는지 확인
  - CLAUDE.md "환경" 섹션에 이 클래스의 버그를 앞으로 방지하기 위한 체크리스트 메모 추가(TextField→NCLOB, select_related+distinct/annotate 조합 점검)
- 이미지 버전 관리 절차대로 1.0.15 빌드·릴리즈까지 진행
- **AWX 플레이북 파일명 통일**: `awx/push_webconfig_to_cmdb.yml`(WebToB)를 `push_apache_config_to_cmdb.yml`/`push_nginx_config_to_cmdb.yml`과 이름 패턴을 맞추기 위해 `push_webtob_config_to_cmdb.yml`로 rename. 참조하던 주석(CLAUDE.md, 두 신규 플레이북, `version_extract.py`)도 갱신, `CHANGELOG.md`/`WORKLOG.md`의 과거 기록은 당시 실제 파일명이라 그대로 둠. `awx/README.md`에 Apache/nginx 플레이북 설명이 통째로 빠져있던 것도 같이 보완(파일 목록 + Job Template 섹션 신규)
- **AWX에서 nginx 설정 push 시 Python 버전 오류 트러블슈팅**: 신규 `push_nginx_config_to_cmdb.yml` 첫 실전 실행에서 `TASK [nginx 설정 파일 원본 읽기]`(`ansible.builtin.slurp`)가 `SyntaxError: future feature annotations is not defined`로 실패한다는 제보(스크린샷)
  - 실패 지점이 커스텀 로직이 아니라 코어 모듈(`slurp`) 자체라는 점, 위쪽 로그의 `[WARNING] Unhandled error in Python interpreter discovery ... Expecting value: line 1 column 1 (char 0)`(빈 응답 → JSON 파싱 실패 → `/usr/bin/python3`로 폴백)까지 종합해 원인은 CMDB/플레이북 코드가 아니라 **대상 서버(POPSAP01)의 Python 버전이 너무 낮다**고 진단 — `from __future__ import annotations`(PEP 563)가 파싱 안 되는 것 자체는 Python 3.7 미만 증상이지만, 최신 ansible-core(`ansible-core/2.18` 문서 링크 확인)가 실제로 요구하는 관리 대상 노드 최소 버전은 그보다 높음
  - 사용자 확인으로 진단 확정: 정상 동작하는 서버는 Python 3.9.x, 실패한 POPSAP01은 3.6.x. 이어서 3.7.x로도 테스트했으나 동일하게 실패 — **최소 3.8 이상 필요, 권장은 3.9**로 결론(3.6/3.7 전부 이 ansible-core 버전과 호환 안 됨)
  - 조치는 CMDB 리포지토리 밖(대상 서버에 Python 3.9 설치 또는 인벤토리 `ansible_python_interpreter`로 이미 설치된 3.9 경로 지정) — 코드 변경 없음
- **`awx/OS_SPECS.md` 신규**: 위 Python 버전 사고를 계기로 "AWX 대상 OS별 스펙"을 기록해두는 문서 요청. 처음엔 호스트별로 만들었다가 사용자 요청으로 OS 단위로 재구성 — AIX/Linux는 SSH+Python 방식이 동일해 요구사항도 동일하게 묶고(3.9 권장), Windows는 애초에 Python 개념이 없고 PowerShell/WinRM(or ansible-core 2.18+ SSH) 기반이라 완전히 별도 섹션으로 분리(WebSearch로 공식 문서 확인 후 작성 — PowerShell 5.1+/Windows Server 2016+, .NET 버전은 출처마다 달라 확정 수치 대신 실측 필요 메모만)
- **WAS(JEUS8) 설정 파싱 추가**: 웹설정에 이어 WAS도 "공통 뷰 + 솔루션별 목록" 구조로 확장 요청, JEUS8부터(`samples/jeus8/domain.xml`). 코딩 전 검토 → Plan 모드로 진행, 확인한 핵심 설계 포인트:
  - "컨테이너" = `<server>` 엘리먼트(사용자 확인)
  - **가장 큰 구조적 차이**: domain.xml 하나가 여러 물리 노드의 컨테이너를 담을 수 있지만 실제 수집은 admin 서버가 떠있는 호스트에서만 이뤄짐 — 그래서 `WasConfigSource.asset`(push 주체=admin 호스트)과 `JeusContainer.asset`(컨테이너 자신의 node-name으로 조회, 소스와 다를 수 있음)을 분리. webconfig 계열은 전부 "소스=자산 하나"였는데 여기서 처음 깨짐
  - 미등록 노드의 컨테이너는 asset=null로 저장(제외 안 함) — 하나의 push에 여러 노드가 섞여 있어 전체를 막으면 다른 정상 컨테이너까지 막히므로
  - `webconfig`와 별도 `was` 앱 신규(`WasConfigSource`/`WasConfigSourceRevision`/`JeusContainer`), `xml.etree.ElementTree`로 파싱(네임스페이스 벗기기 전처리), 버전은 XML `version` 속성에서 명령어/마커 없이 바로 추출(WebToB/Apache/Nginx보다 단순)
  - 검토 중 사용자가 `webtob-connector`(JEUS가 WebToB에 등록되는 설정) 존재를 지적 — `JeusWebtobConnector` 모델 추가해 `registration-id`(=WebToB `*SERVER`(SVRTYPE=JSV) 이름)와 `network-address`(hostname 또는 실제 IP, `Asset.hostname`→`primary_ip` 순으로 매칭)로 실제 `webconfig.WebtobServer`와 교차 연결. `was`가 `webconfig.models`를 import하는 앱 간 의존이 이 기능으로 처음 생김
  - AWX 플레이북(`awx/push_jeus8_config_to_cmdb.yml`)은 admin 서버 호스트에서만 실행해야 한다는 주의사항을 상단 주석 + `awx/README.md`에 명시(워커 노드엔 domain.xml 사본이 없거나 중복 push 위험)
  - 로컬 Docker Compose에서 실제 push(컨테이너 3개) → 기존 `drnrap01` 자산으로 admin 호스트 판별 → 컨테이너별 자산 연결 → WebToB 테스트 데이터(SvrGroup/Server/Vhost) 만들어 재push로 `webtob_server` 사후 해석 확인 → 대시보드 전 화면/검색/서비스명 인라인 편집/재push 시 보존까지 end-to-end 검증. NCLOB `.distinct()` 문제(오늘 앞서 apache/nginx에서 겪은 것과 동일 클래스)가 `JeusContainer.deployed_apps_summary`(TextField)에도 생길 뻔했는데 검색 필터에 to-many 조인이 없어 `.distinct()` 자체를 안 쓰는 방식으로 처음부터 피함 — 쿼리셋 `.query`를 직접 찍어 확인
  - 이어서 사용자 질문("WAS 서비스명이 웹 서비스명 같이 쓰는거지?")에 아니라고 답변 → "WebToB 서비스명을 따라가게 해야 할 것 같다"는 후속 요청. 컨테이너 하나가 webtob-connector 여러 개(이중화)를 가질 수 있고 WebtobServer 하나도 SvrGroup을 거쳐 vhost가 여러 개(M2M) 걸릴 수 있어 "서비스명 하나로 안 좁혀질 수 있음"을 먼저 짚고 논의 — 사용자가 "이중화면 서비스명은 보통 같다"고 확인해줘서 설계 확정: `_resolve_webtob_service_name`이 연결된 vhost들의 service_name을 모아 **공백 아닌 값이 정확히 하나로 겹치면** push 시점에 자동 채움(AUTO-if-resolvable), 갈리거나 연결이 없으면 기존 수기 입력값 유지. WebToB 쪽 값을 나중에 고쳐도 실시간 반영은 안 하고 다음 JEUS push 때만 재해석(앱 간 실시간 트리거는 안 만듦). 실제로 WebToB vhost service_name을 1개/2개로 바꿔가며 재push해 자동 채움/보존 양쪽 다 검증
  - CLAUDE.md에 "WAS 설정" 섹션 신규 추가

## 2026-07-28

- **웹설정 목록 Oracle `ORA-00932`(NCLOB) 500 에러 트러블슈팅·수정**: 어제(07-27) v1.0.11을 폐쇄망에 반입한 뒤 AWX 웹설정 push는 성공했는데 대시보드 웹설정 화면 진입 시 500이 난다는 제보. 사용자가 첨부한 traceback(`ORA-00932: inconsistent datatypes: expected - got NCLOB`)으로 원인 특정
  - `get_webconfig_queryset`(`dashboard/queries.py`, 웹설정 목록)이 `annotate(vhost_count=Count(...), last_changed_at=Max(...))`를 `.values()` 없이 써서 선택된 전체 컬럼으로 암묵적 `GROUP BY`가 걸리는데, `WebConfigSource.raw_content`(`TextField`)가 Oracle에서 NCLOB으로 매핑돼 GROUP BY 대상에 못 들어감. 이 annotate는 07-27(1.0.10) "최근 변경일" 컬럼 추가 때 들어온 코드라 1.0.11 신규 기능은 아니었지만, 로컬(Postgres)에서는 재현이 안 돼 이번에 Oracle 반입 시점에 처음 발견됨
  - 같은 원인으로 `get_webtob_vhost_queryset`(WebToB 설정 목록)도 검색 시 `select_related("source__...")`가 끌고 온 `raw_content`/`extra_sections`가 `.distinct()`에 걸려 같은 오류가 날 수 있어 같이 수정
  - 두 쿼리셋 모두 annotate/distinct 전에 `.defer("raw_content", "extra_sections")`로 해당 필드를 SELECT에서 제외하는 방식으로 수정(목록 템플릿은 두 필드를 안 써서 화면 영향 없음)
  - 데이터 자체는 안전함을 확인: AWX ingest 경로(`WebConfigIngestView` → `sync_webtob`, `@transaction.atomic`)는 이 버그와 무관한 별개 코드라, 어제 push된 데이터는 그대로 두고 이미지만 재배포하면 정상화됨
  - 로컬 Docker Compose(Postgres) 기동해 `Client().force_login()`으로 목록/검색/정렬/상세/엑셀 export 재현 테스트 — 전부 200 확인(단, Postgres에서는 애초에 NCLOB 버그가 재현되지 않으므로 이건 `defer()` 추가로 인한 회귀가 없다는 확인일 뿐, 실제 수정 검증은 폐쇄망 Oracle 반입 후 필요)
  - 발견했지만 보류: `WEBTOB_VHOST_SORT_LOOKUPS`의 `ssl_ciphers` 정렬이 `ssl__required_ciphers`(역시 `TextField`→NCLOB)를 `ORDER BY`해서 같은 이유로 실패할 가능성 있음. 값 길이는 짧아(255자 이내) `CharField` 전환으로 해결 가능하지만 마이그레이션이 필요해 이번엔 미적용
  - 이미지 버전 관리 절차대로 1.0.12 빌드·릴리즈까지 진행
- **웹설정 상세 모달 솔루션 Fix 값에 다음 섹션이 딸려 나오는 문제 트러블슈팅·수정**: 1.0.12 반영 확인 후 사용자가 모달의 "버전정보/최근 반영" 줄바꿈이 화면에서 `\n` 기호로 보이고 실제 개행이 안 된다고 제보
  - `webconfig_detail.html`/모달 주입 JS는 실제 `<br>` 태그를 쓰고 있어 코드상 리터럴 `\n`이 나올 자리가 없어 처음엔 원인 특정에 난항 — 사용자가 폐쇄망 Oracle 캐릭터셋(`KO16MSWIN949`)을 제보했지만 개행문자는 어느 charset에서든 1바이트로 동일해 이 자체가 직접 원인은 아님(다만 Django가 TextField/CharField를 Oracle에서 NCLOB/NVARCHAR2로 매핑하는 이유가 DB가 비UTF-8 charset이기 때문이라는 배경은 확인됨 — 1.0.12 트러블슈팅과 연결됨)
  - 폐쇄망은 반입만 가능하고 코드 실행이 안 돼 사용자가 직접 `manage.py shell`로 `repr()` 찍어 확인 — `solution_fix`에 `...epoll 2026/05/19\\n*DOMAIN`처럼 리터럴 `\n`(백슬래시+n 두 글자) 뒤에 다음 섹션(`*DOMAIN`)까지 붙어있는 것 확인(첫 시도는 여러 줄 명령을 손으로 옮겨 치다 들여쓰기가 깨져 에러 — 들여쓰기가 필요 없는 한 줄짜리 리스트 컴프리헨션 명령으로 재시도해 성공)
  - 원인: AWX 플레이북(`awx/push_webconfig_to_cmdb.yml`)이 버전 마커 뒤 구분자를 Jinja 문자열 이스케이프(`"\n"`, 중첩된 YAML 폴딩 블록 `>-` 안)로 넣었는데, 로컬 sandbox(순수 Jinja2)에서는 정상적으로 실제 개행이 되는 걸 확인했음에도 실제 운영 Ansible에서는 리터럴 텍스트로 남는 사례 발견 — Ansible 내부 템플릿 처리 차이까지는 재현 불가(로컬에 실제 Ansible 없음, 폐쇄망도 격리라 직접 검증 불가)라 원인을 단정하기보다 양쪽 다 방어하는 쪽으로 결론
  - `awx/push_webconfig_to_cmdb.yml`: 마커 줄을 별도 `set_fact`로 뽑아 YAML 리터럴 블록(`|+`, keep 초핑)의 실제 줄바꿈을 쓰도록 변경 — 이스케이프 시퀀스에 전혀 의존하지 않음. 추가로 Jinja2의 `keep_trailing_newline`(꺼져 있으면 템플릿 맨 끝 개행 하나가 렌더링 시 사라짐, Ansible 버전별 기본값 신뢰 어려움) 설정이 뭐든 최소 한 개의 실제 개행이 남도록 블록 끝에 빈 줄을 하나 더 남김 — 로컬에서 `keep_trailing_newline=True`/`False` 양쪽 다 Jinja2로 직접 렌더링해 개행이 남는 것 검증
  - `webconfig/version_extract.py`: 그래도 신뢰 못 하는 파이프라인(YAML/Jinja/JSON/Oracle을 끝까지 로컬에서 재현 못 함)이라 방어 코드 추가 — 마커 파싱 결과에서 리터럴 `\n` 이후는 잘라내도록 `raw_version.split("\\n", 1)[0]` 추가. 로컬 Docker Compose에서 실제 폐쇄망과 동일하게 오염된 마커(`...2026/05/19\n` 뒤에 실제 개행 없이 바로 설정 내용이 이어지는 형태)를 `/api/webconfig/`로 직접 push해 end-to-end로 재현·검증(raw_content엔 리터럴 `\n`이 그대로 남아있어도 solution_version/solution_fix는 깨끗하게 나오고 vhost 파싱도 영향 없음 확인) — 테스트 중 `docker compose exec ... shell -c "여러 줄 명령"`이 셸 레이어를 거치며 이스케이프가 계속 깨져서, 스크립트 파일을 작성해 `docker compose cp`로 컨테이너에 넣고 실행하는 방식으로 전환해 안정적으로 재현
  - 기존에 이미 오염된 값이 저장된 자산은 별도 정리 불필요 — AUTO 필드라 다음 AWX push 때 정상 값으로 자동 갱신됨
  - 이미지 버전 관리 절차대로 1.0.13 빌드·릴리즈까지 진행(AWX 플레이북은 CMDB 이미지에 안 들어가는 별도 배포 산출물이라 이미지 버전과는 무관 — 코드 저장소 커밋만으로 배포, 대상 AWX 서버에 별도 반영 필요)
- **어플리케이션(프로세스 기반) 동작 여부 조회 화면 신규**: OS/웹설정에 이어 "각 서버에 어떤 어플리케이션이 동작 중인지" 보여주는 화면 요청. 코딩 전에 검토부터 진행
  - 설계: 호스트 하나에 어플리케이션이 여러 개 감지될 수 있는 관계형 데이터라 `facts`의 "필드 하나=값 하나" EAV 구조와 안 맞음 — `webconfig`를 별도 앱으로 뺀 것과 같은 판단 기준으로 `processes` 앱 신규 분리. 데이터 소스는 AWX가 각 서버에서 실행한 `ps -ef` 원본, 판정은 Django admin에 정규식 패턴(`ApplicationDefinition`)을 등록해두면 매칭되는 어플리케이션을 자동 감지(`DetectedApplication`, push마다 통짜 재생성) — `FactFieldDefinition`과 같은 "코드 수정 없이 admin에서 확장" 취지
  - 사용자 요구로 추가된 핵심 기능: **admin에서 새 정의를 등록/수정하면 push를 기다리지 않고 기존 스냅샷에도 즉시 소급 반영** — `FactFieldDefinition` 신규 등록 시 `backfill_fact_field` 커맨드를 별도 실행해야 했던 것과 달리, `ApplicationDefinitionAdmin.save_model`을 오버라이드해 저장 시점에 자동으로 재스캔(`processes/matching.py`의 `resync_definition`). 규모가 작아 동기 처리 부담 없고 CLAUDE.md의 "항상 동기 처리" 원칙과도 맞아 별도 커맨드/큐 없이 admin 저장 훅으로 처리하기로 결정
  - 오늘 겪은 Oracle NCLOB GROUP BY/DISTINCT 사고를 반영해 처음부터 방어적으로 설계: `ps -ef` 원본(`raw_output`, TextField)은 목록 쿼리셋에서 `.defer()`로 절대 select 안 하고 상세 화면에서만 별도 조회
  - `raw_output` 변경 이력(diff)은 안 남기기로 결정(프로세스는 PID 등이 수시로 바뀌어 매 push마다 diff를 남기면 노이즈만 커짐) — webconfig의 `WebConfigSourceRevision`과 달리 최신 스냅샷만 유지
  - 로컬 Docker Compose에서 실제 admin 폼 제출까지 거치는 end-to-end 테스트로 검증(정의 없을 때 0건 → admin 등록 시 push 없이 즉시 소급 반영 → 패턴 수정 시 재매칭 → `is_active` 끄면 즉시 제거 → 재push 시 통짜 교체), Playwright로 목록/상세 모달 화면도 스크린샷 확인
  - `ApplicationDefinition.match_pattern`의 admin help_text에 실제 쓸 법한 정규식 예시(PostgreSQL/JEUS/Oracle DB 인스턴스/특정 경로) 추가 — `<br>`/`<code>` 태그를 쓰는데, 이번에 겪은 "\n" 리터럴 이슈 학습을 살려 실제 HTML로 렌더링되는지(Django admin이 help_text를 `|safe`로 렌더링) 직접 화면 확인까지 마침
- **gunicorn WORKER TIMEOUT/SIGKILL 재발 트러블슈팅**: 1.0.12/1.0.13 반영 확인 후에도 폐쇄망 로그에 07-24에 gthread로 고쳤던 것과 동일한 증상(`WORKER TIMEOUT` → `SIGKILL! Perhaps out of memory?`)이 간헐적으로 계속 발견됨
  - 트레이스백이 `gunicorn/workers/sync.py`를 타고 있어 이상하다고 판단 — 현재 Dockerfile은 1.0.8부터 쭉 `--worker-class gthread`인데도 sync로 뜨고 있다는 뜻
  - 파드 안에 `ps`가 없어(슬림 이미지) `/proc/1/cmdline`으로 실제 gunicorn 기동 커맨드 확인 → `--workers 3`만 있고 `--worker-class`/`--threads`가 없는, 1.0.8 이전(1.0.7) 형태의 커맨드였음. 그런데 같은 파드의 `/app/VERSION`은 `1.0.12`로 나와 "앱 코드는 최신인데 gunicorn 기동 커맨드는 옛날" 모순 발생
  - `kubectl describe pod`로 확인해보니 컨테이너 spec에 `Command:`가 명시적으로 박혀있음(옛날 gunicorn 커맨드 그대로) — git 히스토리 전체를 뒤져도 `helm/cmdb-core/templates/deployment.yaml`은 `command`/`args`를 지정한 적이 단 한 번도 없어, 과거 어느 시점에 `kubectl edit`/`set` 등으로 이 Deployment에 수동으로 커맨드가 박힌 것으로 결론(사용자는 본인이 그런 적 없다고 함 — 누가/언제 넣었는지는 감사 로그가 없으면 확정 불가). Helm은 자기 템플릿에 없는 필드는 `helm upgrade`를 아무리 반복해도 안 건드리기 때문에, 이미지 태그(앱 코드)는 계속 최신으로 갱신돼 왔는데 이 수동 커맨드만 계속 살아남아 있었던 것
  - `kubectl patch --type=json`으로 `command` 필드 제거 + `rollout restart` 후 정상화(gthread로 기동) 확인. CMDB 리포지토리 쪽 코드/차트 변경은 없음(운영 클러스터 쪽 드리프트 제거로 해결) — Helm이 관리하는 리소스는 `kubectl edit`/`set`으로 직접 건드리지 말고 항상 values/차트로만 바꿔야 한다는 교훈
- **대시보드 메뉴 명칭 변경**: "자산 대시보드"가 실제로는 OS를 관리하는 화면이 된 상태라 실체에 맞게 명칭 정리 요청. "자산 대시보드"→"OS"(드롭다운 하위 "자산 목록"→"OS 목록"), "웹 설정"→"WEB"(하위 "웹 설정 목록"→"WEB 목록", "WebToB 설정 목록"→"WEBTOB 목록"), "서비스 조회"→"서비스". 내비게이션과 함께 해당 페이지 제목/모달 제목도 일관되게 맞춤(URL·내부 코드명은 유지, 화면 표시 텍스트만 변경)

## 2026-07-27

- **도메인 기반 "서비스 조회" 화면 신규 구축**: 웹설정(WebtoB)이 vhost 기준으로만 조회 가능하던 걸, 서비스명/도메인/hostname/솔루션으로 가로질러 찾는 화면 요구가 나와 설계부터 검토
  - `WebServiceDomain` 모델 신규(`webconfig`). 처음엔 "도메인 하나당 한 행"으로 만들었다가(hostalias까지 쪼개서), 실제로 써보니 vhost 하나가 별칭을 여러 개 가지면 화면이 너무 번잡해진다는 피드백으로 **vhost당 한 행**으로 재설계(`domain`=주 도메인, `aliases`=콤마 문자열). `sync_webtob`이 push마다 통짜 재생성
  - `WebConfigSource.solution_version` 필드 추가(수기 입력 — 설정 파일에 버전 정보가 없어서 자동 추출 불가, 나중에 파일명/설정 파싱으로 자동화할 여지는 남겨둠)
  - 서비스명/솔루션버전 모두 서비스 조회 화면과 웹설정 상세 화면 양쪽에서 편집 가능하고 서로 즉시 반영되도록 동기화(vhost 단위 서비스명은 두 화면이 결국 같은 `WebtobVhost.service_name`을 갱신)
- **다크 테마 → 라이트·고대비 테마 전환**: 연세 있으신 사용자가 다크 테마를 보기 어렵다는 피드백. 대비 감도가 낮아지는 노안엔 다크보다 고대비 라이트가 낫다고 보고, 3가지 목업(차분한 그레이/따뜻한 크림/고대비 큰글씨)을 Artifact로 먼저 보여드리고 "고대비 큰글씨" 안으로 확정 후 적용(`base.html` 전역 오버라이드: 순백 배경, 기본 글자 크기 한 단계 확대, 텍스트 대비 강화, 표 헤더·입력창 테두리 굵게, 상태 태그에 `●`/`✓`/`✕` 기호 병기)
- **디자인 일관성 정리**: 자산 대시보드 컬럼 헤더만 파란색/하늘색 두 톤(고정·수기입력 구분용)이던 걸 다른 탭과 통일해 제거. 대신 수기 입력값 옆에 회색 연필 아이콘(`dash-manual-icon`)을 붙이는 방식으로 대체(처음엔 빨간 점 아이디어였으나 빨강은 이미 `is-danger`=오류·반려 의미라 폐기). 인라인 편집 상호작용도 웹설정 상세만 "편집 버튼+prompt"로 달랐던 걸 다른 화면과 같은 "셀 클릭" 방식으로 통일. 이런 색상/컴포넌트 규칙들을 CLAUDE.md "대시보드 디자인 패턴" 섹션에 신규 정리해 앞으로 화면 추가할 때 기준으로 삼게 함
- **웹설정 변경 이력 신규**: 자산 쪽 승인 이력처럼 웹설정에도 이력을 두고 싶다는 요구 — 다만 웹설정은 "필드 하나=값 하나"가 아니라 관계형 구조(vhost 추가/삭제 등)라 `PendingChange`식 필드 단위 승인 게이트를 그대로 못 씀(구조화 테이블만 승인 대기로 묶으면 상세 화면과 원본 보기가 서로 다른 시점을 보여줘 헷갈림). 검토 후 **읽기 전용 감사 로그**로 결론: `WebConfigSourceRevision`이 `raw_content`가 실제로 바뀔 때만 이전/이후 원본을 남기고(동일 재push는 무시), push 자체는 그대로 즉시 반영 유지. 화면에서 git diff 스타일로 추가=녹색/삭제=빨강 색칠해서 표시, "최신 설정 보기"도 다른 화면과 같은 모달 패턴으로 통일
- **상단 내비게이션 재구성**: "변경 이력"이 최상단 탭으로 따로 있던 걸, "자산 대시보드"/"웹 설정" 드롭다운 하위(목록/변경 이력)로 재배치. 드롭다운 전환 중 활성 항목 글자가 안 보이는 버그 발견·수정 — 최상단 탭용 "배경 투명+밑줄" CSS가 드롭다운 안쪽 항목까지 걸려서, Bulma가 흰 글자로 계산해둔 활성 항목 배경만 지워져 흰 배경 위 흰 글자가 되던 문제(`navbar-start > .navbar-item.is-active`로 범위 좁혀 해결)
- **날짜 컬럼 용어 통일**: 자산은 "생성일"/"최근 변경일", 웹설정은 "최근 반영"으로 제각각이던 걸 정리. 최종적으로 `생성일`은 정보 가치가 낮아 양쪽에서 빼고, **최근 변경일**(실제 값이 바뀐 시점만 — 자산은 `Asset.last_changed_at`, 웹설정은 `WebConfigSourceRevision` 최신 감지 시각)과 **최근 반영일**(내용 변경 무관 마지막 push 시각 — 자산은 신규 노출한 `HostFact.last_seen_at`, 웹설정은 기존 `last_pushed_at`) 두 컬럼으로 양쪽 통일
- **엑셀 다운로드 기능 확대**: 기존엔 업로드만 있고 양식은 사람이 직접 만들어야 했음. 서비스 조회 화면에 다운로드→수정→재업로드 흐름을 먼저 만들면서 매칭 키 문제 발견: 서비스명은 vhost 단위라 처음엔 `(hostname, domain)`으로 매칭하려 했으나, 실제 샘플에 같은 도메인을 http/https vhost 두 개가 나눠 쓰는 경우(`vhost1`/`vhost1_ssl`)가 있어 도메인이 유일하지 않음을 발견 — 매칭 키를 `(hostname, vhost)`로 정정(도메인/별칭은 참고용 컬럼으로만 내보내고 업로드 시 무시). 솔루션버전은 자산 단위 값이라 같은 호스트의 여러 행에 값이 갈리면 "충돌"로 분리해 반영 안 함. 자산 엑셀 업로드/다운로드에도 동일한 다운로드→재업로드 흐름을 추가하면서, 기존 값과 실제로 다른 셀만 "반영 예정"에 잡히도록 diff 비교(타입별 컬럼 직접 비교, 문자열 포맷 차이로 인한 오검출 방지)를 새로 넣음 — 이전엔 값이 채워진 칸은 안 바뀐 것까지 전부 반영 예정으로 떴었음
- `webconfig/excel_import.py`, `webconfig/diff.py` 신규 모듈. 마이그레이션 4건(`WebServiceDomain` 생성/재설계, `solution_version`, `WebConfigSourceRevision`) 적용
- **솔루션 버전/Fix를 수기 입력 → AUTO로 전환**: 실제 서버에서 `wsadmin -version`(`-fullversion`은 이 배포판에서 에러남) 출력을 캡처해보니 `WebtoB 5.0 SP 0 Fix #4 Linux-K2.6_x64 FD16384 B404 epoll 2026/05/19` 형태 — "버전"과 "Fix"로 나눠 표시하고 싶다는 요구. `WebConfigSource.solution_fix` 필드 신규, `webconfig/version_extract.py`가 AWX가 설정 원본 맨 위에 얹어 보내는 `# CMDB_SOLUTION_VERSION: ...` 마커를 "WebtoB 뒤 첫 토큰=버전, 나머지 전부(날짜까지)=Fix"로 분리해 자동 반영. 마커 없는 push는 기존 값 유지(AUTO라고 무조건 비우지 않음). AUTO로 바뀌면서 대시보드의 수기 입력 UI(연필 아이콘)는 제거해 읽기 전용으로
- **AWX 플레이북 `awx/push_webconfig_to_cmdb.yml` 신규**: `wsadmin -version`을 특정 계정(webtob)에서 실행해 위 마커로 얹어 push. 도중에 두 가지 시행착오
  - http.m 경로를 매번 `wcfg`(webtob 계정 셸 alias, 치면 설정 디렉토리로 cd됨)로 자동 탐지해보려 했으나, 실제 서버에서 `bash -i -c`로 강제해도 "command not found" — 로그인 시에만 프로필을 읽는 tty 가드 때문으로 추정. Windows/Linux/AIX가 섞여 있어 OS별 분기까지 필요해지는 걸 감안해 자동 탐지 자체를 포기하고 `webtob_config_path` 변수를 명시하는 방식으로 원복(`wsadmin_path`도 같은 이유로 PATH 의존 대신 전체 경로 유지 — `command` 모듈은 셸을 안 거쳐서 `.bash_profile`의 PATH 확장이 안 먹힘)
  - 이 세 변수를 플레이북 `vars:` 블록에 기본값으로 넣어뒀던 게 버그였음을 발견 — Ansible 변수 우선순위상 play vars가 인벤토리 host_vars보다 높아서, 서버별로 다르게 재정의해도 무시되고 항상 플레이북 값이 이김. `vars:`에서 빼고 각 태스크에서 `{{ 변수 | default('기본값') }}`로 바꿔서 host_vars 재정의가 실제로 먹히게 수정
- **웹설정 목록 줄바꿈·가로 스크롤 정리**: 컬럼(버전/Fix 등)이 늘어나면서 셀 안에서 줄바꿈되던 문제. 자산 대시보드에 있던 "셀 줄바꿈 방지 + 앞 두 컬럼 sticky 고정" CSS를 `base.html` 공통 클래스(`dash-scroll-table`/`dash-sticky-col`)로 뽑아내고, 자산 대시보드 자체도 이 공통 클래스를 쓰도록 같이 리팩터링(기존 전용 CSS 제거) — 웹설정 목록에도 동일 적용
- **정렬 토글을 다른 목록 화면에도 확대**: 자산 대시보드만 컬럼 클릭 시 오름/내림차순이 반전되고 나머지(웹설정 목록/서비스 조회/변경 이력)는 고정 방향이었던 걸 확인 후, `get_dashboard_columns()`의 토글 로직을 `build_sort_columns()`(`dashboard/queries.py`)로 범용화해 세 화면에 전부 연결
- **웹설정 상세 모달 보강**: `*NODE`절의 `LimitRequestBody` 필드 신규 추출·표시. 버전/Fix도 모달 상단에 표시(같은 줄 · 로 구분, 최근 반영은 줄바꿈해서 다음 줄)
- **웹 설정 목록 정리**: Node 컬럼 제거(hostname과 자산의 hostname이 결국 같은 값이라 중복이라는 지적 — 모델 필드는 admin 식별용으로 유지, 목록/모달 표시만 정리)
- **WebToB 설정 목록 신규**(`/dashboard/webconfig/vhosts/`): 기존 목록·서비스 조회가 서버 단위/도메인 중심이라 "vhost를 행 단위로 여러 서버 가로질러" 보는 화면이 따로 필요하다는 요구로 신설. `WebtobVhost` 하나 = 행 하나로 모달 vhost 카드의 값(도메인/별칭/Port/DocRoot/LimitRequestBody(NODE 상속)/SSL·Protocols·RequiredCiphers/Logging/ErrorLog/서비스명)을 전부 컬럼으로, 관계형인 SvrGroup/Server/URI는 모달을 또 띄우지 않고 콤마 요약 문자열로 한 칸에("표 안에서 다 끝내기" 요구). 요약 컬럼 3개만 정렬 미지원(DB 컬럼이 아니라 Python에서 합친 문자열이라 정렬 기준이 없음), 나머지는 전부 정렬 가능. "웹 설정" 드롭다운 하위에 배치
- **검토만 하고 보류한 것 두 가지**: (1) 웹설정에도 자산의 `FactFieldDefinition` 같은 동적 필드 시스템을 둘지 — WebToB 속성은 종류가 한정적이고(facts처럼 예측 불가한 게 아님), 이미 EAV를 피하려고 `webconfig`를 분리한 취지와 맞지 않아 기각, 필요한 필드는 그때그때 모델에 추가하는 현행 유지로 결론. (2) WebToB `Server`가 나중에 JEUS와 1:1 매핑될 걸 대비한 설계 — 지금 구조(이름으로 파싱 시점에 FK 연결)가 이미 이런 확장에 자연스럽게 맞아서 미리 손댈 필요 없다고 판단, `WebtobServer.name`으로 나중에 매칭하면 된다는 방향만 기록

## 2026-07-24

- **동적 필드(AUTO)에서 raw_facts 리스트 안 값 추출 가능 여부 확인**
  - `extract_json_path`(`facts/dynamic_fields.py`)는 각 단계마다 dict인지만 확인하고 리스트를 만나면 바로 `None`을 반환 — 리스트 인덱싱/필터링은 현재 미지원. 같은 함수를 재사용하는 `facts/approval.py`의 고정 컬럼 승인 비교 로직도 동일 제약
  - 실사용자가 준 실제 AWX facts 샘플로 구조 확인: `ansible_facts.default_ipv4`/`default_ipv6`는 dict라서 지금 코드로 바로 등록 가능(`ansible_facts.default_ipv4.macaddress` 등), 반면 `ansible_facts.<interface>.ipv6`나 `all_ipv4_addresses`처럼 진짜 리스트인 값은 인덱스 경로 지원 없이는 추출 불가 — 현재는 미해당(필요 시 숫자 인덱스 파싱을 `extract_json_path`에 추가하는 정도의 작은 확장으로 가능하다고 결론만 내려둠, 구현은 보류)
- **`ansible_facts.default_ipv4.macaddress` 동적 필드 신규 등록**: admin 대신 Django shell로 `FactFieldDefinition` 생성 + `backfill_fact_field` 커맨드로 소급 반영, 실제 push API(`POST /api/facts/`)로 샘플 자산(`DRNRAP01`)을 등록해 MAC 주소 값이 정상 추출되는 것까지 종단 검증
- **로컬 개발 DB 정리**: 기존 테스트 자산 6개(형식이 뒤섞여 있던 더미 데이터, hostvars 접두사 유무가 호스트마다 달랐음)를 전부 삭제하고 사용자가 준 실제 샘플 하나만 남김. 곁가지로 발견한 죽은 `FactFieldDefinition` 2개(`ansible_facts.ansible_processor_vcpus`, `ansible_facts.ansible_distribution_version` — 접두사 버그가 고쳐지기 전 등록되어 지금 포맷에서는 항상 빈 값, 후자는 고정 컬럼 `os_version`과 완전 중복)도 함께 삭제
- **재사용 가능한 샘플 데이터 저장**: `samples/facts/drnrap01.json`에 push 페이로드 형식으로 정리해 커밋, `samples/facts/README.md`에 재push용 curl 명령 기록
- **변경 승인 설정을 `ApprovalFieldConfig` → `FactFieldDefinition` 통합으로 리팩터링**
  - 문제: 승인 대상 지정이 `ApprovalFieldConfig`라는 별도 모델이라 동적(AUTO) 필드는 `FactFieldDefinition` 등록과 `ApprovalFieldConfig` 등록을 매번 두 번 해야 했고, 두 모델의 `value_type`이 서로 검증 없이 따로 입력돼 드리프트 가능성도 있었음(리뷰 중 발견)
  - `FactFieldDefinition.Source`에 `FIXED`(고정 컬럼 8개 전용, `facts.approval.FIXED_FIELD_PATHS`와 매칭) 추가, `requires_approval` BooleanField 신설. `ApprovalFieldConfig` 모델은 완전 삭제하고 `PendingChange.field_config`(→`ApprovalFieldConfig`) FK를 `field_definition`(→`FactFieldDefinition`) 하나로 단순화 — `stage_governed_changes`가 이제 `FactFieldDefinition.objects.filter(requires_approval=True)` 한 루프만 돎
  - admin 검증 추가: FIXED 소스는 key가 `FIXED_FIELD_PATHS`에 있는 값이어야 함, MANUAL 소스는 `requires_approval` 체크 자체를 막음(대시보드 수기입력은 항상 즉시 반영이라 의미 없는 설정이라 실수 방지 차원)
  - `backfill_fact_field` 관리 커맨드에 FIXED/MANUAL 가드 추가(기존엔 admin 액션에만 MANUAL 가드가 있고 커맨드 자체엔 없던 구멍)
  - 마이그레이션 3단계(스키마 추가 → 기존 `ApprovalFieldConfig`/`PendingChange` 데이터를 새 구조로 이관 + 나머지 6개 FIXED 컬럼도 `requires_approval=False`로 미리 시딩 → 스키마 정리)로 작성, 역방향(rollback)도 구현
  - 로컬에서 실제 push로 end-to-end 검증: 승인 대상 필드 값 변경 시 즉시 반영 안 되고 `PendingChange` 대기, 대시보드에서 승인하면 반영·`last_changed_at` 갱신, 반려하면 유지되는 것까지 확인. 이후 `ansible_facts.default_ipv4.macaddress`(AUTO 동적 필드)도 `requires_approval` 체크 한 번으로 동일하게 승인 흐름을 타는 것까지 검증(고정 컬럼 전용이 아니게 된 것 확인)
  - CLAUDE.md/`helm/cmdb-core/templates/NOTES.txt`의 `ApprovalFieldConfig` 언급을 `FactFieldDefinition` 기준으로 갱신
- **CLAUDE.md 문서 보강**: `key`(dot-path)가 리스트를 못 타는 제약을 "신규 수집 항목 추가" 섹션에 명시, "테스트/검증" 섹션 신규 추가(자동화 테스트 사실상 없음 + 로컬 curl/shell 재현 검증이 관례라는 점, `samples/facts/` 재사용 안내)
- **폐쇄망 K8s 500 에러 트러블슈팅(원인 미확정, 재현 안 됨)**: replica 2개 환경에서 "AWX push와 동시에 대시보드 접속 시 500"이라는 제보. 코드 리뷰로 두 가설 도출 — (1) `apply_pending_change`(`facts/approval.py`)가 `pending_change.asset.hostfact`를 `getattr` 없이 직접 접근해서 HostFact가 없는 상태면 터질 수 있음(다만 이건 pod 개수와 무관), (2) 더 유력하게는 gunicorn worker 3개 × replica 2개인데 `CONN_MAX_AGE` 미설정이라 요청마다 Oracle 커넥션을 새로 열어서, push 트랜잭션(동적 필드 개수만큼 순차 처리라 꽤 오래 걸림)과 대시보드 조회가 겹치면 폐쇄망 Oracle 계정의 세션 제한에 걸릴 가능성. 실제 `kubectl logs`의 `ORA-` 에러 코드로 확정 필요 — 재현 안 돼서 이번엔 보류
- **Hostname/IP 고정 컬럼 동작 검증(Playwright 신규 도입)**: 로컬에 브라우저 자동화 도구가 없어서 `.venv`에 Playwright+Chromium 설치, 로그인 → 뷰포트 강제로 좁혀 스크롤 발생 → 스크롤 전/후 셀 좌표(`getBoundingClientRect`) 비교로 Hostname/IP만 고정되고 나머지 컬럼은 흘러가는 것 확인(스크린샷도 저장)
- **가로 스크롤 시 셀 줄바꿈 버그 수정**: 컬럼이 많아지면 테이블이 옆으로 안 넓어지고 셀 안에서 줄바꿈되며 행이 세로로 늘어나던 문제. 원인은 `white-space: nowrap`이 sticky 컬럼(Hostname/IP)에만 걸려있고 나머지 일반 컬럼엔 없어서, Bulma `table-layout:auto` + `is-fullwidth`(`width:100%`) 조합에서 브라우저가 테이블을 넓히는 대신 텍스트를 줄바꿈하는 쪽을 택했던 것. `.asset-table th/td` 전체에 `white-space: nowrap` 추가로 해결(`table-container`는 이미 Bulma 기본값으로 `overflow-x` 처리돼 있어서 CSS 한 줄로 충분). 검증은 실제 동적 필드 8개를 임시 등록해 컬럼 17개까지 늘린 뒤 일반 노트북 해상도(1280px, 인위적 축소 없이)에서 자연스럽게 가로 스크롤 뜨는 것/셀이 한 줄(41px) 유지되는 것을 Playwright로 확인 후 테스트용 필드·계정은 정리
- **이미지 버전/릴리즈 프로세스 신규 도입**: 버전을 WORKLOG 프로즈로만 추적하다 실제 배포 버전과 어긋난 적이 있어(WORKLOG엔 1.0.4가 최신인데 실제론 1.0.6까지 나가 있었음) 루트 `VERSION` 파일을 단일 기준으로 도입. `CHANGELOG.md` 신규(배포자 관점 릴리즈 노트, WORKLOG와 역할 분리). 앱 코드가 바뀐 push마다 버전업 → 이미지 빌드 → `docker save`+7z 압축 → CHANGELOG 갱신 → 커밋/push → GitHub Release(압축 이미지 첨부) 자동 처리하는 절차를 CLAUDE.md에 명문화, 로컬에 없던 7-Zip/GitHub CLI를 winget으로 설치. 첨부파일 용량이 계속 쌓이지 않게 "최신 3개 릴리즈만 첨부파일 유지, 오래된 건 태그/노트만 남기고 첨부파일 삭제" 정책도 추가
  - v1.0.7(승인 설정 통합 리팩터링 + nowrap 수정), v1.0.8(gunicorn worker 변경) 실제 릴리즈까지 진행
- **gunicorn worker 클래스 `sync` → `gthread` 변경**: 폐쇄망에서 간헐적으로 잡힌 `WORKER TIMEOUT`(gunicorn이 요청 자체를 읽는 단계, `no URI read`)에 대한 대응. 지난번(07-22) AWX push 크기 문제로 났던 것과는 다른 종류(Django 뷰 진입 전에 죽음)로 판단. 유휴 TCP 연결에서 sync 워커가 `recv()`에 블로킹되다 30초 워커 타임아웃에 걸려 SIGKILL당하는 걸로 추정(폐쇄망 NAT/방화벽이 연결을 조용히 끊는 경우 흔한 패턴). 사용자 규모(~30명) 기준 `gthread`(워커 2 × 스레드 4)가 표준적인 선택이라 판단해 `Dockerfile` 변경, 컨테이너 단독 기동으로 정상 동작 확인 후 적용
- **커밋 전 사용자 확인 절차 명문화**: 세션 종료/이미지 릴리즈 절차처럼 CLAUDE.md에 "자동으로 처리한다"고 적힌 흐름도 예외 없이, 실제 `git commit` 직전엔 항상 무엇이 바뀌었는지 보여주고 확인받도록 CLAUDE.md에 규칙 추가(빌드/버전업/CHANGELOG 작성 등 커밋 이전 준비 작업까지는 자동 진행 가능하지만 커밋 자체는 확인 후 실행)
- **웹 서버 설정(WebtoB) 시각화 기능 신규 구축**: OS ansible facts와는 별개로 웹서버 설정 파일을 파싱해 vhost 중심으로 보여주는 기능. 방향성부터 검토 후 진행
  - 설계: `facts`/`FactFieldDefinition`(EAV, 필드 하나=값 하나)과는 성격이 달라(vhost/server/uri가 호스트당 여러 개, 서로 이름으로 참조) 별도 앱 `webconfig`로 분리. `WebConfigSource`가 원본 텍스트 전체 보관, push마다 구조화 테이블 통짜 재생성(diff 없음, 승인 절차 미적용)
  - WebtoB `http.m` 전용 파서(`webconfig/parsers.py`) 신규 작성: 따옴표 안 콤마/주석(`#`, 줄 중간에도 나옴) 구분, 들여쓰기로 항목 연속 여부 판단. 실제 샘플 3개(`samples/webtob/`)로 파싱 결과 전수 검증
  - 자산 매칭 방식 정정: 처음엔 push payload에 별도 hostname 필드를 쓰려 했으나, 파일명이 실제 호스트명과 다를 수 있다는 사용자 지적으로 **설정 내용의 `*NODE` 절 항목 이름**을 hostname으로 쓰는 걸로 변경(자산 신규 생성은 안 함 — facts push로 이미 등록된 자산만 대상)
  - VHost가 중심 엔티티, SSL/SvrGroup/Server/Uri가 이름으로 참조하는 구조를 파싱 시점에 실제 FK로 연결. 도중에 발견한 모델링 이슈: `SvrGroup`/`Uri`의 `VhostName`이 콤마로 여러 vhost를 한 번에 지정하는 경우가 있어(`"vhost1,vhost1_ssl"`) 단일 FK가 아니라 ManyToMany로 수정
  - `EXT`/`ALIAS`/`LOGGING`/`ERRORDOCUMENT`처럼 검색 가치 낮은 절은 구조화 테이블 대신 JSON(`extra_sections`)에만 보관, VhostName 없는 SvrGroup/Server(정적 파일용 공용 그룹)는 vhost 상세 화면에서 자연히 제외
  - 대시보드에 "웹 설정" 탭 신규(목록/vhost 중심 상세 화면, 원본 설정은 접어서 표시). 샘플 3개 전부 push → 관계(Server→SvrGroup→VHost 역추적 포함) 정확히 맺어지는 것 DB 조회로 검증, Playwright로 실제 렌더링까지 스크린샷 확인
  - **후속 개선**: (1) 목록에서 행 클릭 시 페이지 이동 대신 모달로 띄우도록 변경 — 기존 상세 페이지는 그대로 두고, 목록 페이지 JS가 그 페이지를 fetch해서 `#webconfig-content`만 잘라 모달에 주입하는 방식(새 엔드포인트 없이 재사용, `DOMParser`로 클라이언트에서 파싱). Playwright로 URL 이동 없이 모달만 뜨는 것 확인
  - (2) 목록 검색을 자산 hostname뿐 아니라 vhost의 `hostname`/`hostalias`(도메인)까지 포함하도록 확장(`Q` OR + `.distinct()`로 중복 행 방지), 실제 도메인 문자열로 검색해 검증
  - (3) vhost별 "서비스명" 수기 입력 필드 추가 검토·구현: `WebtobVhost.service_name` 필드 추가는 간단하지만, 기존 `sync_webtob`이 push마다 vhost를 통째로 지우고 재생성하는 구조라 수기값이 다음 push에 날아가는 문제를 먼저 발견 — vhost만 `(source, name)` 기준 `update_or_create`로 upsert하고 이번 push에 없는 vhost만 삭제하는 방식으로 sync 로직 변경(SvrGroup/Server/Uri는 수기 데이터 없어서 기존 통짜 재생성 유지). 편집은 vhost 카드의 "편집" 버튼 → `prompt()` → 새 엔드포인트(`/dashboard/webconfig/vhost/<id>/service/`)로 즉시 저장(승인 절차 없음, 자산 MANUAL 필드와 동일 원칙). Apache/Nginx 확장 가능성도 물어봐서 검토만 함 — 지금 구조(kind 디스패치)는 수집 파이프라인만 재사용되고 파서/모델/화면은 웹서버 종류마다 새로 만들어야 한다는 결론(WebtoB의 VHost/SvrGroup 개념이 Apache/Nginx엔 그대로 없음)
  - (4) SSL 정보에 인증서 경로만 보이던 걸 Protocols/RequiredCiphers도 같이 표시하도록 상세 템플릿 보강
  - **마이그레이션 적용 도중 Docker 자체가 응답 없음 상태가 되어(`docker version`까지 멈춤) 검증 중단** — (3)/(4) 변경사항은 코드 작성까지만 완료, 실제 동작 검증(마이그레이션 적용, service_name 보존 확인, SSL 표시 확인)은 다음 세션에서 Docker 재시작 후 이어서 해야 함

## 2026-07-23

- **대시보드 컬럼 레이아웃 개선**
  - 고정 컬럼을 두 그룹으로 분리(`LEADING_FIXED_COLUMNS`: Hostname/IP/OS, `TRAILING_FIXED_COLUMNS`: 생성일/최근 변경일). 동적 필드가 그 사이에 끼도록 순서 재배치해 생성일/최근변경일이 동적 컬럼 오른쪽으로 이동(`dashboard/queries.py`, `asset_list.html`)
  - Hostname/IP 컬럼은 가로 스크롤해도 화면에 고정 표시(`position: sticky`, Bulma 다크테마 CSS 변수 재사용해 배경색 처리)
- **수기 입력(MANUAL) 동적 필드 신규 구축**
  - `FactFieldDefinition`에 `source`(AUTO/MANUAL) 구분 추가. push 동기화(`sync_dynamic_fields`)가 AUTO만 대상으로 하도록 수정 — MANUAL 필드는 push로 값이 덮어써지지 않음(핵심 설계 포인트)
  - 곁가지로 발견한 버그 수정: `coerce_fact_value`의 BOOL 처리가 문자열 `"false"`도 진위값 True로 취급해 체크 해제해도 항상 "true"로 저장되던 문제
  - 대시보드 값 입력 UX를 세 단계로 반복 개선: (1) 자산 행마다 전체 수기 필드를 한 모달에 모아 편집 → (2) 셀 클릭 시 그 자리에서 바로 입력(인라인) → (3) 필드 수가 늘어날 걸 감안해 셀 클릭 시 작은 팝업(모달)으로 그 필드 하나만 편집하는 방식으로 최종 정착. 테두리/점선으로 편집 가능 컬럼을 표시하는 것도 시도했다가 "보기 안 좋다"는 피드백으로 제거, 헤더 글자색(Bulma info색)만으로 구분
  - 저장은 승인 절차 없이 즉시 반영 + `Asset.last_changed_at` 갱신
  - CLAUDE.md에 AUTO/MANUAL 구분, 승인 절차 미적용, 최근 변경일 갱신 조건 등 반영
- **수기 필드 엑셀 일괄 업로드**
  - `openpyxl`/`et-xmlfile` 신규 vendoring(`vendor/wheels`, 순수 파이썬이라 폐쇄망 문제없음)
  - `hostname / 필드label / 필드label...` 형식 업로드 → 헤더 검증(label 매칭, 중복 라벨 거부) → 행별 검증(hostname 불일치, 값 형식 오류는 반영 안 함, 빈 셀은 해당 필드 값 유지) → 미리보기 → 확정 2단계 흐름(`dashboard/excel_import.py`)
  - 신규 자산은 생성하지 않음(기존 자산만 갱신 대상), 확정 시 영향받은 자산마다 `last_changed_at` 갱신
  - 대시보드 네비에 업로드 메뉴 추가
- **선택형(CHOICE) 값 타입 추가**
  - `FactFieldDefinition.value_type`에 `CHOICE` 추가, 선택지 목록을 담는 자식 모델 `FactFieldChoice` 신규(관계형 테이블로 분리 — ArrayField/JSONField로 욱여넣지 않기로 한 기존 원칙과 동일선상)
  - admin에서 필드 등록 화면에 선택지 인라인 추가해 필드+선택지를 한 번에 관리
  - 저장 시(대시보드 팝업 편집·엑셀 업로드 양쪽 다) 제출값이 등록된 선택지에 있는지 서버에서 검증(`is_valid_choice`), 팝업 편집 UI는 CHOICE 타입이면 텍스트 입력 대신 `<select>` 드롭다운으로 렌더링
- 위 기능들 전부 Django 테스트 클라이언트/curl 기반 재현 테스트로 저장·검증·오류 케이스까지 확인 후 진행(정상 저장, 형식 오류, hostname 불일치, 선택지 밖 값, BOOL 체크/해제 등)

## 2026-07-22

- **첫 폐쇄망 반입 후 AWX facts push 장애 대응**
  - 증상: AWX Job이 gunicorn `WORKER TIMEOUT`으로 30초 뒤 SIGKILL, 응답 없이 실패. `kubectl logs`에 아무것도 안 찍혀서 원인 파악이 막힘
  - 원인 1: `Dockerfile`의 gunicorn이 `--access-logfile` 없이 떠서 요청 로그 자체가 안 남고, `settings.py`에 `LOGGING` 설정이 없어 `DEBUG=False`에서 예외도 콘솔에 안 찍힘 → 둘 다 추가(`--access-logfile -`/`--error-logfile -`, Django `LOGGING`)
  - 원인 2: 실제 hang의 진짜 원인은 `ansible.builtin.uri` 모듈이 대용량 payload에서 이 환경(AWX 실행환경)과 조합했을 때만 걸리는 문제로 확인(curl로는 같은 환경/같은 payload에서도 즉시 응답). AWX 실행환경에 `which`는 없지만 `curl`은 있음을 확인
  - 원인 3(진짜 버그): 승인 미지정 hypervisor 필드가 빈 문자열로 올 때 `PositiveIntegerField`에 그대로 넣어서 `ValueError` 500 발생(`num_cpu`/`memory_mb`) → `facts/views.py`에서 빈 문자열을 `None`으로 정규화하도록 수정
  - 원인 4(진짜 버그): `ansible_facts` 딕셔너리 원본 키는 `ansible_` 접두사가 없는데(`distribution`, `default_ipv4` 등) 코드가 접두사 붙은 키(`ansible_distribution` 등)를 찾고 있어서 OS 정보가 항상 빈 값으로 저장되던 버그 발견, `facts/views.py`/`facts/approval.py`의 dot-path 수정
  - 위 수정들을 묶어 이미지 재빌드 `1.0.1`→`1.0.2`→`1.0.3` (마지막은 아래 대시보드 변경 포함)
- vCenter/Nutanix는 추후 연동하기로 하고 1차는 AWX(ansible facts)만으로 운영하기로 결정. 하이퍼바이저 메타데이터(Cluster/Power State 등)는 AWX 인벤토리 Source Variables 매핑 전까지 비어있는 게 정상이라는 점 확인(코드 변경 불필요, 이미 범용 설계)
- **대시보드 개선**
  - 기본 컬럼을 Hostname/IP/OS/생성일/최근 변경일로 정리(Cluster/Power State/Last Seen 제거, `dashboard/queries.py`/`asset_list.html`)
  - 행 클릭 시 해당 자산의 raw facts를 Bulma 모달 팝업으로 예쁘게(들여쓰기 pretty-print) 보여주는 기능 추가(`/dashboard/assets/<id>/facts/` 신규 엔드포인트, 로그인 필요)
  - 다크 테마 적용: vendoring된 Bulma 1.0.4가 CSS 변수 기반 다크 테마를 내장하고 있어 `<html data-theme="dark">`만 추가. 상단 메뉴 선택 시 배경색 채움 대신 밑줄(box-shadow) 강조로 커스텀
  - 로컬(docker-compose)에서 테스트 계정/샘플 자산 데이터로 컬럼·팝업·다크테마 전부 curl 기반으로 동작 확인 후 정리
- **동적 필드(Number 타입) 표시/검색 버그 수정**
  - 등록한 동적 필드(`processor_cores` 등)를 백필해도 대시보드에 값이 안 보이는 문제 발견: `value_text`가 `None`이 아니라 빈 문자열(`""`)로 저장된 값 우선순위 로직 때문에 `value_number`/`value_date`로 폴백을 안 하던 버그. 빈 문자열도 "값 없음"으로 취급하도록 `dashboard/queries.py`의 `build_rows` 수정
  - 겸사겸사 동적 필드 검색(`is_searchable`)이 항상 `value_text__icontains`만 봐서 Number/Date 타입 필드는 검색이 항상 실패하던 문제도 같이 수정 — Number/Date는 값 파싱 성공 시 정확값 매칭, Text/Bool은 기존처럼 부분일치
  - 로컬에서 숫자 검색(정확매칭)·빈 결과 케이스까지 curl로 재검증 후 이미지 재빌드 `1.0.4`

## 2026-07-21

- **폐쇄망 반입/배포 절차 점검**: Oracle 계정 준비 시 필요한 권한(CREATE SESSION/TABLE/SEQUENCE/TRIGGER 등)·테이블스페이스 쿼터·문자셋(AL32UTF8) 확인 필요성 정리. 테이블 자체는 Helm migrate Job(post-install/pre-upgrade hook)이 자동 생성하므로 DBA가 미리 만들 필요 없음을 확인
- Harbor push/pull 인증 관련 점검: `imagePullSecrets`가 차트에 없다는 점을 확인했으나, 사내 Harbor 프로젝트가 public이라 현재는 불필요하다고 결론(추후 private 전환 시 대응 필요)
- **`values-prod.yaml` 반입 방식 정리**: 비밀번호 등 실제 값은 외부망→폐쇄망으로 옮기지 않고 폐쇄망 내부에서 직접 작성하기로 결정. 레이아웃만 반입할 수 있도록 `values-prod.yaml.example` 신규 작성, `DEPLOY.md` 4단계가 이 예시 파일을 가리키도록 정리, 실수 커밋 방지를 위해 `.gitignore`에 `values-prod.yaml` 추가
- `CLAUDE.md`에 "세션 종료" 절차(작업 종료 신호 시 WORKLOG 갱신→커밋→push) 명문화
- NodePort/서비스 포트 개념 정리: `service.port`(클러스터 내부용)와 `service.nodePort`(외부 접근용, 미지정 시 랜덤)가 다르다는 점, AWX `cmdb_base_url`은 nodePort 기준으로 설정해야 함을 확인. `helm install`에 `-f` 미지정 시 차트 기본 `values.yaml`의 placeholder(`change-me` 등)로 조용히 배포될 위험이 있음을 확인

## 2026-07-16

- 로컬 기동 스크립트(`start.ps1`)로 Docker Compose 기동 확인, AWX facts push를 흉내낸 샘플 payload로 API 동작 검증 (X-API-Key 인증, 자산 생성, 재push 시 upsert)
- 동적 필드(EAV) 구조가 설계 의도대로 동작하는지 실측 검증: 필드 등록 후 신규 push는 자동 반영, 기존 데이터는 `backfill_fact_field` 커맨드로 소급 반영 필요함을 확인
- `FactFieldDefinition` 백필을 admin 화면에서 버튼(액션)으로 실행할 수 있도록 개선 (`facts/dynamic_fields.py`의 `backfill_field` 공용 함수로 리팩터링, `FactFieldDefinitionAdmin`에 액션 추가)
- **변경 승인 워크플로우 신규 구축**
  - `ApprovalFieldConfig`(승인 대상 필드를 코드 변경 없이 admin에서 지정, 고정 컬럼/동적 필드 공통), `PendingChange`(대기/승인/반려 상태와 이전값·새값 기록) 모델 추가
  - 신규 자산은 승인 없이 즉시 반영, 기존 자산의 지정 필드 값 변경만 대기열에 쌓임. 대기 중 재push는 동일 값이면 무시, 다른 값이면 별도 건으로 스택
  - `Asset.last_changed_at` 추가(승인 반영 시점 기록), 자산 대시보드에 생성일/최근 변경일 정렬 컬럼 추가
  - 변경 이력 전용 조회 화면(`/dashboard/changes/`) 신설: 검색/상태필터/정렬/페이지네이션 + 대기 건 승인·반려까지 가능
  - 여러 건이 한꺼번에 들어오는 상황 대비, 체크박스로 여러 건을 골라 일괄 승인/반려하는 기능 추가
- **대시보드 로그인 전환**: 관리를 admin 대신 대시보드 중심으로 가져가기로 하면서 대시보드 전체(자산 목록 포함)에 로그인 요건 추가 (Django 기본 인증 재사용, 별도 계정 체계 없음). Django admin은 `ApprovalFieldConfig` 같은 저빈도 설정용으로 최소화
- CLAUDE.md에 변경 승인/대시보드 로그인 원칙 반영, LOCAL_ACCESS.md 갱신
- 여러 건이 동시에 대기 상태로 들어오는 상황 재현용 테스트 데이터 생성 (호스트별 CPU 증설 push 등), 대시보드 일괄 승인/반려 실제 클릭 흐름까지 검증
- **AWX → CMDB 연동 플레이북 추가** (`awx/`): ansible facts는 그대로, 하이퍼바이저 메타데이터는 인벤토리 소스에서 정규화한 `cmdb_*` 변수로 조립해서 `/api/facts/`로 push. vCenter/Nutanix 인벤토리 플러그인의 실제 hostvar 이름은 구성에 따라 달라서 플레이북이 직접 파싱하지 않고 AWX 인벤토리 소스 설정(Source Variables)으로 정규화하도록 분리. vCenter/Nutanix 연결 전, AWX ansible facts만 있는 상태에서도(하이퍼바이저 변수 미설정) 에러 없이 동작함을 실제 push로 검증
- **폐쇄망 Helm 배포 준비**
  - Oracle 19c용 `oracledb`(thin mode, Instant Client 불필요) 드라이버와 프로덕션용 `gunicorn`, 정적 파일 서빙용 `whitenoise`를 `vendor/wheels`에 오프라인 설치 가능하도록 추가(cryptography 등 전이 의존성 포함)
  - Dockerfile을 `collectstatic` + `gunicorn` 기반 운영용으로 개편, DEBUG=False·gunicorn 조합으로 실제 기동해 정적 파일 서빙까지 검증(로컬 dev는 docker-compose가 여전히 runserver로 오버라이드하므로 영향 없음)
  - `helm/cmdb-core/` 차트 신규 작성: Deployment/Service(NodePort)/ConfigMap/Secret(또는 `existingSecret`)/마이그레이션 Job(post-install,pre-upgrade hook). `helm lint`/`helm template`로 렌더링 검증
- 루트에 `DEPLOY.md` 추가: 외부망 빌드 → 폐쇄망 반입(`docker save`/`load`, Harbor push) → Oracle 준비 → `values-prod.yaml` 작성(민감정보 git 미포함) → `helm install` → 배포 확인 → AWX 연동까지 이어지는 운영 배포 절차와 체크리스트. `helm/cmdb-core/README.md`(차트 옵션 레퍼런스), `awx/README.md`(AWX 설정)와 상호 링크
- **대시보드 디자인 적용**: 코딩 전에 실제 화면 데이터(변경 이력 표, 상태 배지, 승인/반려 버튼)를 Pico.css/Bulma/Tabler로 각각 렌더링한 비교 아티팩트를 먼저 만들어 보고 결정 — Bulma 채택
  - Bulma CSS를 CDN 링크 대신 `dashboard/static/dashboard/css/`에 직접 커밋해 이미지에 포함(폐쇄망에서도 외부 요청 없이 서빙)
  - 공통 `base.html`(navbar + 메시지 배너)로 자산 대시보드/변경 이력/로그인 3개 화면 레이아웃 통일, 기존 기능(정렬·검색·페이지네이션·개별 및 일괄 승인/반려)은 그대로 유지하고 스타일만 교체
  - 그 과정에서 whitenoise가 항상 켜져 있어 로컬 dev에서 새 정적 파일이 반영 안 되는 문제 발견 → `DEBUG=False`(운영)에서만 whitenoise를 쓰도록 수정, 로컬은 계속 Django 기본 정적 서빙 사용
  - 로컬(runserver)과 운영 이미지(gunicorn+collectstatic) 양쪽 다 재빌드해서 화면·정적파일·승인 플로우 재검증

## 2026-07-15

- GitHub 원격 저장소(`https://github.com/guv03/cmdb-core.git`) 연동, 첫 커밋 push
- CLAUDE.md 초안 작성 및 아키텍처 논의 반영해 갱신 (커밋 규칙 섹션 포함)
- 계획 수립: AWX 단일 수집 경로, 동적 필드(EAV) 시스템, 읽기 전용 대시보드 설계
- Django 프로젝트 초기 구축
  - `core`: Asset 모델, 인증(AWXAPIKeyAuthentication), reconciliation
  - `facts`: HostFact 모델, FactFieldDefinition/HostFactValue(동적 필드), facts push API, backfill 커맨드
  - `dashboard`: 읽기 전용 자산 목록 화면 + API (검색/정렬/페이지네이션, 동적 필드 컬럼 지원)
- Django 6.0.7 / DRF 3.17.1 / psycopg[binary] 3.3.4 / python-dotenv 1.2.2로 의존성 확정
- 폐쇄망 이전 대비 `vendor/wheels`에 의존성 wheel 전체 vendoring, 오프라인 설치 검증
- Dockerfile / docker-compose.yml / .env.example 작성, 로컬 Docker Compose 전체 플로우 검증
  (facts push, 인증 실패, 재조합, 대시보드, 동적 필드 등록·백필)
- 로컬 기동 스크립트 `scripts/start.ps1` 추가
- 로컬 접속 정보 파일 `LOCAL_ACCESS.md` 추가 (git 미포함)
