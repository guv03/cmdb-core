# CMDB 프로젝트
Django + DRF 기반 CMDB. 자산 자체(신규 생성)는 AWX push 경로 하나뿐이다. 다만 일부 필드 값(수기 입력 동적 필드)은 대시보드에서 사람이 직접 입력할 수 있다 — 아래 "신규 수집 항목 추가" 참고.

# 환경
- 로컬 개발: Docker Compose + PostgreSQL
- 운영(폐쇄망): Kubernetes + Oracle 19c
- Oracle 호환을 위해 Postgres 전용 SQL/필드(ArrayField, HStoreField 등)는 쓰지 말 것. JSONField는 조회 불가능한 아카이브 용도로만 쓰고, 필터/정렬이 필요한 값은 실제 컬럼이나 동적 필드로 승격할 것.

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
- 두 경우 모두 "필드 하나 = 값 하나"만 다루며, 범용 플러그인/계산식 시스템(다른 필드를 조합한 계산값 등)으로 확장하지 않는다.
- `source`에는 `FIXED`라는 세 번째 값도 있는데, 이건 "신규 수집 항목 추가"용이 아니라 아래 변경 승인 설정 전용이다 — `HostFact`의 고정 컬럼(os_family/num_cpu 등 8개, `facts.approval.FIXED_FIELD_PATHS` 참고)을 승인 대상으로 지정할 수 있게 `FactFieldDefinition`에 메타데이터만 얹어둔 것이며 `is_visible=False`로 대시보드 동적 컬럼에는 노출되지 않는다.

# 변경 승인
- 이 승인 절차는 AWX push로 들어오는 값 변경에만 적용된다. 대시보드에서 사람이 직접 입력하는 MANUAL 동적 필드 값은 이 절차를 거치지 않고 저장 즉시 반영된다(이미 사람이 확인하고 넣는 값이라 별도 승인이 불필요하다고 판단).
- 신규 자산(첫 push)은 승인 없이 즉시 반영한다. 이미 존재하는 자산의 값이 바뀌는 경우만 대상.
- 승인이 필요한 필드는 코드 변경 없이 admin의 `FactFieldDefinition` 목록에서 `requires_approval` 체크박스로 지정한다(고정 컬럼/동적 필드 공통, `FactFieldDefinition` 하나로 관리 — 별도 승인 설정 모델 없음). 지정 안 된 필드는 기존과 동일하게 push 즉시 반영.
- push로 들어온 값이 지정 필드의 현재 반영값과 다르면 `PendingChange`로 대기열에 쌓이고, 대시보드(`/dashboard/changes/`)에서 승인해야 실제 반영된다. 반려도 가능. admin에서도 동일한 승인/반려 액션을 제공하지만 일상적인 처리는 대시보드 기준.
- 대시보드 변경 이력 화면에서 여러 건을 체크박스로 골라 한 번에 일괄 승인/반려할 수 있다(운영에서 여러 변경이 한꺼번에 들어오는 상황 대비).
- 대기 중 재push 시: 새 값이 기존 대기 건과 동일하면 무시, 다르면 별도 건으로 쌓는다(덮어쓰지 않음).
- 같은 필드에 여러 건이 대기 중일 때 하나를 승인/반려해도 나머지 대기 건은 자동 정리되지 않는다 — 필요 시 수동으로 함께 정리(대시보드 일괄 처리로 가능).

# 대시보드
- Django admin과 별개로 검색/정렬/페이지네이션이 되는 조회 화면을 둔다. 신규 자산은 push로 즉시, 승인 대상 필드의 값 변경은 승인 시점에 반영된다.
- 관리는 대시보드 중심으로 가고 Django admin은 최소화한다(주로 `FactFieldDefinition` 필드 정의/승인 대상 지정 같이 자주 안 바뀌는 설정용). 그래서 승인/반려도 admin이 아니라 대시보드의 변경 이력 화면에서 처리한다.
- 대시보드 전체(자산 목록 포함)는 로그인 필요. 계정은 Django 기본 인증(admin과 동일 계정) 그대로 재사용, 별도 권한 체계 새로 만들지 않는다.
- 최근 추가(`생성일`)/최근 변경(`최근 변경일`) 정렬 컬럼 제공. `최근 변경일`은 승인된 push 변경 시점뿐 아니라 MANUAL 동적 필드를 대시보드에서 수정한 시점에도 갱신된다.
- 변경 이력(대기/승인/반려 전체)은 `/dashboard/changes/`에서 조회 + 대기 건은 승인/반려 처리까지 가능.
- MANUAL 동적 필드는 자산 목록의 "관리" 컬럼 → "편집" 버튼(모달)으로 값을 입력/수정한다. 변경 이력(`/dashboard/changes/`)에는 남지 않는다 — 승인 대상이 아니기 때문.
- Hostname/IP 컬럼은 가로 스크롤 시에도 고정 표시된다(`position: sticky`).

# 배포
- 이미지는 Harbor로 push 후 K8s Deployment
- NodePort 방식 서비스 노출
- Helm 차트는 `helm/cmdb-core/` (자세한 사용법은 그 안의 README.md). 민감정보(시크릿키/DB 비밀번호/AWX API 키)는 이 리포지토리의 `values.yaml`에 커밋하지 않고 별도 values 파일이나 `existingSecret`으로 주입.
- 마이그레이션은 `manage.py migrate`를 실행하는 Helm hook Job이 install/upgrade마다 자동 처리(별도 워커/큐 없이 동기 처리 원칙과 동일선상).
- 운영 이미지는 `gunicorn`으로 기동, 정적 파일(주로 Django admin CSS/JS)은 `whitenoise`로 이미지 안에서 직접 서빙(별도 nginx/CDN 없음). 로컬 개발은 여전히 `docker-compose.yml`이 `runserver`로 오버라이드.
- Oracle 19c 연결은 `oracledb`(thin mode, Oracle Instant Client 불필요이므로 폐쇄망 vendoring이 단순함)를 사용. `vendor/wheels`에 oracledb/gunicorn/whitenoise 및 의존성(cryptography 등) 포함.

# 커밋 규칙
- 형식: `<type>: <한글 설명>` (Conventional Commits 기반, 설명만 한글)
- type: `feat`(새 기능), `fix`(버그 수정), `docs`(문서만 변경), `refactor`(동작 변화 없는 구조 개선), `test`(테스트 추가/수정), `chore`(빌드/설정/의존성 등 잡무)
- 예: `feat: 동적 필드 정렬 기능 추가`, `fix: hostname 정규화 누락 수정`

# 세션 종료
- 사용자가 작업을 종료한다는 취지로 말하면(예: "끝낼게", "여기까지", "작업 종료" 등), 아래를 순서대로 처리한다.
  1. `WORKLOG.md`에 이번 세션 작업 내용을 정리해서 추가(기존 형식 유지, 새 날짜는 위에 추가)
  2. 커밋 규칙에 따라 변경사항(WORKLOG.md 포함) 커밋
  3. 원격에 push
- 커밋할 변경사항이 전혀 없으면(WORKLOG.md 갱신도 불필요한 경우) 커밋/push는 건너뛴다.
