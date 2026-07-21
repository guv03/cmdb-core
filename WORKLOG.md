# 작업 일지

일 단위로 진행한 작업을 기록한다. 새 날짜는 위에 추가한다.

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
