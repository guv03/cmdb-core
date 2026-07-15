# CMDB 프로젝트
Django + DRF 기반 CMDB. 자산 데이터 수집 경로는 AWX push 하나뿐이다.

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
- 그래서 자주 안 쓰는/새로 생기는 항목은 고정 컬럼을 추가하지 않고, admin에서 필드 정의만 등록하면 자동 추출·저장되고 대시보드 정렬/검색까지 코드 수정 없이 되는 동적 필드 구조를 쓴다.
- 이 패턴은 "raw facts의 한 키를 컬럼으로 승격"하는 용도로만 쓰고, 범용 플러그인/계산식 시스템으로 확장하지 않는다.

# 대시보드
- Django admin과 별개로 검색/정렬/페이지네이션이 되는 읽기 전용 조회 화면을 둔다(수정은 AWX push로만 발생).

# 배포
- 이미지는 Harbor로 push 후 K8s Deployment
- NodePort 방식 서비스 노출

# 커밋 규칙
- 형식: `<type>: <한글 설명>` (Conventional Commits 기반, 설명만 한글)
- type: `feat`(새 기능), `fix`(버그 수정), `docs`(문서만 변경), `refactor`(동작 변화 없는 구조 개선), `test`(테스트 추가/수정), `chore`(빌드/설정/의존성 등 잡무)
- 예: `feat: 동적 필드 정렬 기능 추가`, `fix: hostname 정규화 누락 수정`
