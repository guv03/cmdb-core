# 작업 일지

일 단위로 진행한 작업을 기록한다. 새 날짜는 위에 추가한다.

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
