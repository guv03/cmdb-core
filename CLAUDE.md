# CMDB 프로젝트
Django + DRF 기반 CMDB. 자산 자체(신규 생성)는 AWX push 경로 하나뿐이다. 다만 일부 필드 값(수기 입력 동적 필드)은 대시보드에서 사람이 직접 입력할 수 있다 — 아래 "신규 수집 항목 추가" 참고. OS 팩트 외에 웹서버 설정(WebtoB 등) 시각화도 다룬다 — 아래 "웹 서버 설정" 참고.

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
- AUTO의 `key`(dot-path)는 `extract_json_path`(`facts/dynamic_fields.py`)가 각 단계마다 dict인지만 확인하고 순회한다 — 경로 중간에 JSON 리스트가 나오면 그 다음부터 무조건 `None`이 된다(인덱싱/필터링 미지원). 예: `ansible_facts.default_ipv4.macaddress`처럼 값이 dict로만 이어지면 등록 가능하지만, `ansible_facts.<interface>.ipv6`처럼 리스트를 거쳐야 하는 값은 지금 구조로는 못 뽑는다.
- `source`에는 `FIXED`라는 세 번째 값도 있는데, 이건 "신규 수집 항목 추가"용이 아니라 아래 변경 승인 설정 전용이다 — `HostFact`의 고정 컬럼(os_family/num_cpu 등 8개, `facts.approval.FIXED_FIELD_PATHS` 참고)을 승인 대상으로 지정할 수 있게 `FactFieldDefinition`에 메타데이터만 얹어둔 것이며 `is_visible=False`로 대시보드 동적 컬럼에는 노출되지 않는다.

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
- `WebConfigSource`가 push된 원본 텍스트를 통째로 보관(`raw_content`, 감사/재현용). 종류(`kind`, 현재는 `webtob`만)별로 자산당 1개, push마다 구조화 테이블을 전부 지우고 다시 만든다(diff 없이 통짜 교체 — 승인 절차 대상 아님, push 즉시 반영).
- 파서(`webconfig/parsers.py`)와 재생성 로직(`webconfig/sync.py`)은 `kind`별로 분리해서 등록(`PARSERS`/`SYNC_FUNCS` dict). 새 웹서버 종류 추가 시 이 두 군데에 함수 하나씩 등록하면 됨 — WebtoB/Apache/Nginx는 개념 자체가 달라서 억지로 공통 프레임워크로 통일하지 않음.
- WebtoB 구조: `VHost`가 중심 엔티티, `SSL`은 VHost가 이름으로 참조, `SvrGroup`/`Uri`는 `VhostName` 속성으로 VHost를 참조하는데 **콤마로 여러 vhost를 한 번에 지정하는 경우가 있어 ManyToMany**(예: `VhostName = "vhost1,vhost1_ssl"`). `Server`는 `SVGNAME`으로 `SvrGroup`을 참조. 파싱 시점에 이름으로 실제 FK/M2M을 연결해서 저장(문자열 매칭이 아니라 진짜 DB join으로 역추적 가능 — Server→SvrGroup→VHost).
- `VhostName` 없는 `SvrGroup`/`Server`(정적 파일 처리용 공용 그룹 등)는 대시보드 vhost 상세 화면에서는 노출 안 함(vhost 기준 화면이라 자연히 빠짐 — 별도 필터링 코드 불필요, `vhost.svrgroups.all()`로 순회하면 애초에 그 vhost에 안 걸린 svrgroup은 안 나옴).
- `EXT`/`ALIAS`/`LOGGING`/`ERRORDOCUMENT` 등 검색 가치가 낮은 절은 구조화 테이블로 안 만들고 `WebConfigSource.extra_sections`(JSON)에만 보관 — 지금은 원본 설정 펼쳐보기로만 노출, 조회 대상 아님.
- 자산 신규 생성은 이 경로로 안 함(자산 생성은 facts push 경로 하나뿐이라는 원칙 유지) — hostname은 push payload가 아니라 **설정 내용의 `*NODE` 절 항목 이름**을 기준으로 기존 자산을 찾고, 없으면 에러(먼저 facts push로 자산이 등록돼 있어야 함).
- 대시보드 `/dashboard/webconfig/`에서 목록(호스트/종류/vhost 수) → 상세(vhost별 카드, 원본 설정은 `<details>`로 접어둠) 확인. 샘플 데이터는 `samples/webtob/`.

# 대시보드
- Django admin과 별개로 검색/정렬/페이지네이션이 되는 조회 화면을 둔다. 신규 자산은 push로 즉시, 승인 대상 필드의 값 변경은 승인 시점에 반영된다.
- 관리는 대시보드 중심으로 가고 Django admin은 최소화한다(주로 `FactFieldDefinition` 필드 정의/승인 대상 지정 같이 자주 안 바뀌는 설정용). 그래서 승인/반려도 admin이 아니라 대시보드의 변경 이력 화면에서 처리한다.
- 대시보드 전체(자산 목록 포함)는 로그인 필요. 계정은 Django 기본 인증(admin과 동일 계정) 그대로 재사용, 별도 권한 체계 새로 만들지 않는다.
- 최근 추가(`생성일`)/최근 변경(`최근 변경일`) 정렬 컬럼 제공. `최근 변경일`은 승인된 push 변경 시점뿐 아니라 MANUAL 동적 필드를 대시보드에서 수정한 시점에도 갱신된다.
- 변경 이력(대기/승인/반려 전체)은 `/dashboard/changes/`에서 조회 + 대기 건은 승인/반려 처리까지 가능.
- MANUAL 동적 필드는 자산 목록의 "관리" 컬럼 → "편집" 버튼(모달)으로 값을 입력/수정한다. 변경 이력(`/dashboard/changes/`)에는 남지 않는다 — 승인 대상이 아니기 때문.
- Hostname/IP 컬럼은 가로 스크롤 시에도 고정 표시된다(`position: sticky`).

# 테스트/검증
- 자동화 테스트 스위트는 사실상 없다(`*/tests.py`는 있지만 비어있음, `manage.py test` 실행해도 0건). 변경 검증은 로컬 Docker Compose에서 curl로 실제 API를 호출하거나 `manage.py shell`로 재현해 직접 확인하는 방식이 관례.
- `samples/facts/`에 실제 AWX facts push 페이로드 샘플을 모아둔다(`README.md`에 재push용 curl 명령 포함). 동적 필드/승인 흐름 등을 검증할 때 새로 지어내지 말고 여기 있는 걸 재사용할 것. 웹서버 설정 샘플은 `samples/webtob/`(호스트네임_http.m 원본 파일).

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
  3. `docker save cmdb-core:<새 버전> -o cmdb-core-<새 버전>.tar`로 추출 후 `7z a cmdb-core-<새 버전>.tar.7z cmdb-core-<새 버전>.tar`로 압축한다(7-Zip: `C:\Program Files\7-Zip\7z.exe`, PATH에 없으면 이 경로로 직접 호출).
  4. `CHANGELOG.md` 맨 위에 새 버전 섹션을 추가해 이번 릴리즈에 포함된 변경사항을 정리한다. `WORKLOG.md`가 개발 과정의 디버깅/검토 기록이라면, `CHANGELOG.md`는 "이 배포 버전에 뭐가 들어갔는지"를 배포자 관점에서 간결하게 정리하는 파일.
  5. **여기서 커밋 전 확인**: `VERSION`/`CHANGELOG.md` 변경사항을 보여주고 승인받은 뒤 커밋 + push한다.
  6. `gh release create v<새 버전> cmdb-core-<새 버전>.tar.7z --title v<새 버전> --notes "<CHANGELOG.md의 해당 버전 섹션 내용>"`으로 GitHub Release를 만들고 압축한 이미지를 첨부한다(`gh`도 PATH에 없으면 `C:\Program Files\GitHub CLI\gh.exe`로 직접 호출). `gh auth login`은 사용자가 미리 해뒀다고 가정 — 로그인 안 돼 있으면 진행 못 하니 사용자에게 알릴 것.
  7. `.tar`/`.tar.7z` 산출물은 리포지토리에 커밋하지 않는다(`.gitignore`에 이미 제외 설정, GitHub Release 첨부파일로만 배포).
  8. Release 업로드까지 끝나면 로컬(스크래치패드 등)에 남은 `.tar`/`.tar.7z` 파일은 지운다 — 원본은 GitHub Release에 있으니 필요하면 거기서 받으면 됨.
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
