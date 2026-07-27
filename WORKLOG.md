# 작업 일지

일 단위로 진행한 작업을 기록한다. 새 날짜는 위에 추가한다.

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
