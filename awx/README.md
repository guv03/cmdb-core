# AWX → CMDB push 플레이북

## 파일

- `push_facts_to_cmdb.yml` — ansible facts + 하이퍼바이저 메타데이터를 CMDB(`POST /api/facts/`)로
  push하는 메인 플레이북. CMDB는 vCenter/Nutanix API를 직접 호출하지 않으므로 이 플레이북이
  CMDB로 자산 데이터가 들어가는 유일한 경로다. AWX Job Template에 그대로 연결해서 쓴다.
- `push_webconfig_to_cmdb.yml` — WebToB 설정 파일(`http.m`)을 CMDB(`POST /api/webconfig/`)로
  push하는 플레이북. 자산 자체는 생성하지 않음(위 facts 플레이북으로 먼저 등록돼 있어야 함).
- `inventory_source_vars.example.yml` — vCenter/Nutanix 인벤토리 소스의 hostvar를
  플레이북이 기대하는 정규화된 변수명으로 매핑하는 예시(참고용, 실제 환경에 맞게 조정 필요).

## AWX 설정

### 1. 인벤토리 소스

vCenter/Nutanix dynamic inventory 플러그인이 노출하는 hostvar 이름은 구성한 properties에
따라 제각각이라, 플레이북이 직접 파싱하지 않는다. 대신 인벤토리 소스의 **Source Variables**
`compose`에서 아래 6개 변수로 정규화해둔다 (`inventory_source_vars.example.yml` 참고):

- `cmdb_source_platform` — `vcenter` / `nutanix` (고정 문자열로 넣으면 됨)
- `cmdb_vm_uuid`
- `cmdb_cluster_name`
- `cmdb_power_state`
- `cmdb_num_cpu`
- `cmdb_memory_mb`

매핑을 안 해둔 값은 CMDB에 null로 전달되고, CMDB 쪽에서 physical/unknown 등 기본값으로
처리한다 (실패하지 않음).

### 2. Job Template — facts push

- Playbook: `awx/push_facts_to_cmdb.yml`
- Inventory: 위에서 설정한 vCenter/Nutanix dynamic inventory
- Credential: `cmdb_api_key`를 담은 Custom Credential Type을 만들어 연결하거나,
  최소한 Extra Variables에 평문으로 넣지 말고 AWX Credential/Vault로 주입할 것
- Extra Variables 예시:
  ```yaml
  cmdb_base_url: http://cmdb.internal:8000
  cmdb_validate_certs: true
  ```
- ansible facts 수집이 실패한 호스트는 이 플레이북 자체가 그 호스트에서 실행되지 않으므로
  (AWX가 연결 실패 호스트를 자동으로 제외) 별도 처리 불필요 — CLAUDE.md 원칙대로
  "facts push 시점에만 반영되면 충분".

### 3. Job Template — WebToB 설정 push

- Playbook: `awx/push_webconfig_to_cmdb.yml`
- Inventory: WebToB가 설치된 호스트 그룹(facts push와 같은 자산이어야 함 — hostname으로
  기존 자산을 찾으므로 순서상 facts push가 먼저 한 번은 돌아 있어야 함)
- Credential: facts push와 동일한 `cmdb_api_key` 재사용 가능
- Extra Variables 예시(모든 호스트에 동일하게 적용되는 값만 — 아래 참고):
  ```yaml
  cmdb_base_url: http://cmdb.internal:8000
  cmdb_validate_certs: true
  ```
- **`webtob_account`/`wsadmin_path`/`webtob_config_path`는 서버마다 값이 다를 수 있어서
  Extra Variables에 넣지 말고 인벤토리의 호스트별(또는 같은 값을 쓰는 그룹별) 변수로
  등록할 것.** AWX Extra Variables는 `-e`로 넘어가서 인벤토리 host_vars보다도 우선순위가
  더 높기 때문에, 여기 넣으면 호스트별로 다르게 설정해둔 값이 있어도 전부 무시되고 Extra
  Variables 쪽 값 하나로 덮여버린다 — 플레이북에 실제로 값이 하나도 없을 때만 각 태스크에
  박아둔 기본값(`webtob`, `/app/webtob/bin/wsadmin`, `/app/webtob/config/http.m`)으로
  대체되도록 만들어뒀으니, 서버마다 다르면 인벤토리 쪽에, 전부 같으면 그냥 기본값을 쓰거나
  인벤토리 `group_vars/all`에 한 번만 넣으면 된다. Windows/Linux/AIX 등 OS마다, 서버마다
  WebToB 설치 위치와 계정 환경(예: `wcfg` 같은 셸 alias)이 제각각이라 자동 탐지 대신
  명시적으로 값을 주는 쪽으로 정했다 — 자동 탐지는 플랫폼별 분기가 늘어나는 데 비해 서버
  수가 아주 많지 않다면 얻는 게 적어서 기각.
- `wsadmin -version` 출력(예: `WebtoB 5.0 SP 0 Fix #4 Linux-K2.6_x64 FD16384 B404 epoll 2026/05/19`)을
  설정 원본 맨 위에 `# CMDB_SOLUTION_VERSION: ...` 주석으로 얹어서 같이 보낸다. CMDB가 이
  마커를 파싱해 버전(`5.0`)/Fix(나머지 전부, 날짜까지)를 자동으로 채운다 — 대시보드에서
  수기로 입력할 필요 없음(자세한 파싱 규칙은 CMDB 리포지토리의 `webconfig/version_extract.py`,
  `CLAUDE.md`의 "솔루션 버전/Fix는 AUTO" 참고).
- `wsadmin -version` 조회가 실패해도(권한 문제 등) 설정 push 자체는 그대로 진행된다
  (`failed_when: false`) — 이 경우 CMDB 쪽 solution_version/solution_fix는 기존 값 유지.

### 4. 로컬 테스트

CMDB를 로컬 Docker Compose로 띄운 상태에서, 임의 값으로 API를 직접 호출해 CMDB 쪽 동작을
먼저 검증하고 싶다면 CMDB 리포지토리의 `LOCAL_ACCESS.md`를 참고 (facts/webconfig push API 섹션).
