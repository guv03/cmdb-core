# AWX → CMDB push 플레이북

## 파일

- `push_facts_to_cmdb.yml` — ansible facts + 하이퍼바이저 메타데이터를 CMDB(`POST /api/facts/`)로
  push하는 메인 플레이북. CMDB는 vCenter/Nutanix API를 직접 호출하지 않으므로 이 플레이북이
  CMDB로 자산 데이터가 들어가는 유일한 경로다. AWX Job Template에 그대로 연결해서 쓴다.
- `push_webtob_config_to_cmdb.yml` — WebToB 설정 파일(`http.m`)을 CMDB(`POST /api/webconfig/`)로
  push하는 플레이북. 자산 자체는 생성하지 않음(위 facts 플레이북으로 먼저 등록돼 있어야 함).
- `push_apache_config_to_cmdb.yml` / `push_nginx_config_to_cmdb.yml` — Apache/nginx 설정 파일을
  CMDB(`POST /api/webconfig/`)로 push하는 플레이북. WebToB와 달리 설정 파일 안에 서버 자신을
  가리키는 절이 없어(`*NODE` 같은 게 없음) `inventory_hostname`을 payload에 직접 실어 보낸다.
- `push_jeus_config_to_cmdb.yml` — JEUS 7/8/8.5/9(domain.xml 레이아웃 공통, `kind=jeus`)
  도메인 설정 파일(`domain.xml`)을 CMDB(`POST /api/was/`)로 push하는 플레이북. WAS는
  `webconfig`와 다른 별도 앱(`was`)이다. **admin 서버가 떠있는 호스트에서만 실행할 것** —
  domain.xml은 도메인 전체(여러 물리 노드)를 기술할 수 있지만 파일 자체는 admin 서버
  호스트에만 있다. JEUS 6는 파일 구조가 달라 이 플레이북 대상이 아님(`kind=jeus6`,
  아래 `push_jeus6_config_to_cmdb.yml` 참고).
- `push_jeus6_config_to_cmdb.yml` — JEUS 6(`JEUSMain.xml` + 컨테이너별
  `servlet_engine{N}/WEBMain.xml`, `kind=jeus6`) 설정을 CMDB(`POST /api/was/`)로 push하는
  플레이북. **admin 서버 개념이 없어(JEUSMain.xml 하나 = 물리 노드 하나) 위 `push_jeus_config_to_cmdb.yml`과
  달리 JEUS6 노드 전부를 인벤토리 대상으로 실행해야 함.** `JEUSMain.xml`과 그 밑의 모든
  `servlet_engine*/WEBMain.xml`을 같이 읽어 `files`(파일명 → 원본 텍스트 dict)로 한 번에
  push한다(`kind=jeus`의 `content` 단일 문자열과 다름). **같은 호스트에 OS 계정만 다르게
  해서 JEUS6가 여러 개 뜰 수 있어(예: `ddorap01`에 `jeuscm`/`jeuslt` 각각) `jeus6_instance_name`
  (보통 OS 계정명)을 반드시 채워야 함 — 계정별로 인벤토리 host 항목을 나누거나 Job Template을
  나눠서 실행할 것.**
- `inventory_source_vars.example.yml` — vCenter/Nutanix 인벤토리 소스의 hostvar를
  플레이북이 기대하는 정규화된 변수명으로 매핑하는 예시(참고용, 실제 환경에 맞게 조정 필요).
- `push_vcenter_systems_to_cmdb.yml` / `push_vcenter_systems_instance_tasks.yml` /
  `push_vcenter_vm_detail_tasks.yml` — vCenter REST API를 직접 호출해 VM 목록을
  CMDB(`POST /api/systems/`)로 push하는 플레이북. 위 facts/webconfig/was 플레이북과 달리
  개별 호스트가 아니라 vCenter 인스턴스 단위(여러 대 순회 가능)로 딱 한 번씩 실행된다(기본
  `hosts: localhost`, 방화벽 때문에 특정 서버를 경유해야 하면 `systems_collector_host`로
  바꿀 수 있음 - 아래 "8. 경유 서버" 참고) - CMDB의 `systems` 앱, CLAUDE.md의 "시스템" 섹션
  참고. VM별 상세/게스트 조회는 `include_tasks`로 분리된 `push_vcenter_vm_detail_tasks.yml`을
  VM 목록으로 루프 호출(Ansible이 `block`에 `loop`를 지원하지 않아 별도 파일로 뺌).
- `push_nutanix_systems_to_cmdb.yml` / `push_nutanix_systems_instance_tasks.yml` — 위와 같은
  설계로 Nutanix Prism Central API를 호출해 VM 목록을 CMDB로 push하는 플레이북.

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
- **AIX/구버전 Linux처럼 기본 Python이 낮은(3.8 미만) 호스트는 `gather_facts`가 실패한다**
  (AWX의 ansible-core가 요구하는 module_utils 문법이 3.8+, 자세한 내용은 `OS_SPECS.md`
  참고). AIX Toolbox 등으로 신버전 Python을 별도 경로에 설치했다면(PATH의 `python3`는
  안 바뀌는 경우가 많음) 그 호스트/그룹의 인벤토리 변수로 인터프리터 경로를 지정 —
  플레이북 자체는 수정할 필요 없음:
  ```
  ansible_python_interpreter=/opt/freeware/bin/python3.9
  ```

### 3. Job Template — WebToB 설정 push

- Playbook: `awx/push_webtob_config_to_cmdb.yml`
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

### 4. Job Template — Apache/nginx 설정 push

- Playbook: `awx/push_apache_config_to_cmdb.yml` / `awx/push_nginx_config_to_cmdb.yml`
- Inventory: Apache/nginx가 설치된 호스트 그룹(facts push와 같은 자산이어야 함 — WebToB와
  동일하게 facts push가 먼저 한 번은 돌아 있어야 함)
- Credential: facts push와 동일한 `cmdb_api_key` 재사용 가능
- Extra Variables 예시:
  ```yaml
  cmdb_base_url: http://cmdb.internal:8000
  cmdb_validate_certs: true
  ```
- **`apache_config_path`/`apachectl_path`(또는 `nginx_config_path`/`nginx_path`)는 서버마다
  값이 다를 수 있어서 WebToB와 같은 이유로 Extra Variables가 아니라 인벤토리 호스트별/그룹별
  변수로 등록할 것.** 기본값은 각각 `/etc/httpd/conf.d/httpd-ssl.conf`(`apachectl`),
  `/etc/nginx/nginx.conf`(`nginx`) — 실제 설치 경로가 다르면 재정의 필요.
- `apachectl -version`/`nginx -v` 출력을 설정 원본 맨 위에 `# CMDB_SOLUTION_VERSION: ...`
  주석으로 얹어서 같이 보낸다(WebToB와 같은 방식). Apache는 출력 두 줄 중 첫 줄만, nginx는
  기본적으로 stderr로 나가는 출력을 우선 사용 — 조회가 실패해도 push 자체는 그대로 진행되고
  이 경우 solution_version은 기존 값 유지.

### 5. Job Template — JEUS(7~9) 설정 push

- Playbook: `awx/push_jeus_config_to_cmdb.yml`
- Inventory: **각 JEUS 도메인의 admin 서버가 떠있는 호스트만**(워커/매니지드 노드는 대상에
  넣지 말 것 — domain.xml 사본이 없거나, 있어도 같은 도메인이 중복 push됨). facts push가
  먼저 한 번은 돌아 있어야 함.
- Credential: facts push와 동일한 `cmdb_api_key` 재사용 가능
- Extra Variables 예시:
  ```yaml
  cmdb_base_url: http://cmdb.internal:8000
  cmdb_validate_certs: true
  ```
- **`jeus_domain_xml_path`는 서버마다 값이 다를 수 있어서 다른 플레이북과 같은 이유로
  Extra Variables가 아니라 인벤토리 호스트별/그룹별 변수로 등록할 것.** 기본값은
  `/app/jeus/domains/jeus_domain/config/domain.xml`.
- 버전 정보는 명령어 실행 없이 `domain.xml` 루트의 `version` 속성에서 CMDB가 직접 뽑는다 —
  WebToB/Apache/Nginx와 달리 마커 주석을 얹을 필요가 없음.
- domain.xml에 담긴 각 컨테이너(`<server>`)는 자기 `node-name`으로 별도 자산에 연결된다
  (이 push를 보낸 admin 호스트와 다를 수 있음). 아직 자산으로 등록 안 된 노드의 컨테이너는
  일단 자산 미연결 상태로 저장되고, 나중에 그 노드가 facts push되면 다음 JEUS push 때
  자동으로 연결된다.

### 6. Job Template — vCenter 시스템 정보 push

- Playbook: `awx/push_vcenter_systems_to_cmdb.yml` (인스턴스별 실제 작업은
  `awx/push_vcenter_systems_instance_tasks.yml`에 `include_tasks`로 분리)
- Inventory: 아무 inventory나 상관없음 - `hosts: localhost`로 딱 한 번만 실행되고 관리 대상
  서버에 SSH 접속하지 않는다(각 호스트 facts push와 완전히 분리된 흐름). vCenter가 여러 대라
  어느 호스트가 어느 vCenter에 속하는지 미리 알 수 없어서, 호스트별로 조회하는 대신 가진
  vCenter를 전부 통째로 조회해 VM 목록을 CMDB로 보내고 CMDB가 hostname으로 기존 자산과
  매칭한다(자세한 설계는 CMDB 리포지토리 `CLAUDE.md`의 "시스템" 섹션 참고).
- Credential: `cmdb_api_key`는 facts push와 동일한 것 재사용 가능. vCenter 인증 정보
  (`vcenter_instances`의 username/password)는 평문 Extra Variables에 넣지 말고 Vault-encrypted
  변수나 Survey password 타입 필드로 주입할 것.
- Extra Variables 예시:
  ```yaml
  cmdb_base_url: http://cmdb.internal:8000
  cmdb_validate_certs: true
  vcenter_instances:
    - name: vcenter01.corp.local
      base_url: https://vcenter01.corp.local
      username: svc-cmdb@vsphere.local
      password: "{{ vault_vcenter01_password }}"
    - name: vcenter02.corp.local
      base_url: https://vcenter02.corp.local
      username: svc-cmdb@vsphere.local
      password: "{{ vault_vcenter02_password }}"
  ```
- CMDB 쪽은 "물리 장비(ESXi 호스트)가 기본 단위, VM은 그 위에 관계형으로 딸린 OS"로
  모델링돼 있어(`systems` 앱) 이 플레이북은 `GET /api/vcenter/host`(물리 호스트 목록)와
  `GET /api/vcenter/vm`(VM 목록) 둘 다 조회해서 `hosts`/`vms` 두 배열로 나눠 push한다 -
  각 VM은 자기 상세 응답의 `host` 필드(호스트 moref)로 어느 물리 호스트에 속하는지 표시.
- **반입 전 확인 필요**: vSphere REST API 응답 스키마는 vCenter 버전(6.5/7.0/8.0)마다 조금씩
  다를 수 있어서, 이 플레이북은 공식 문서로 확인된 필드(VM 목록의 name/power_state/cpu_count/
  memory_size_MiB, 게스트 identity의 host_name/ip_address)만 구조화해서 보내고 **물리
  호스트의 CPU 코어/메모리 총량/모델 같은 실제 하드웨어 스펙은 구조화하지 않았다** - 호스트
  목록 응답 항목 전체를 CMDB의 `extra`(참고용 아카이브)에 그대로 실어 보낸다. 디스크·NIC
  상세도 마찬가지로 VM 상세 응답 원본을 `extra`에 보관. 실제 vCenter의
  `https://<vcenter>/apiexplorer`로 `GET /api/vcenter/host/{host}` 등의 응답 구조를 확인한
  뒤 필요하면 `push_vcenter_systems_instance_tasks.yml`의 필드 매핑을 넓히면 된다.

### 7. Job Template — Nutanix 시스템 정보 push

- Playbook: `awx/push_nutanix_systems_to_cmdb.yml` (인스턴스별 실제 작업은
  `awx/push_nutanix_systems_instance_tasks.yml`에 분리) - 위 vCenter 플레이북과 완전히 같은
  설계(개별 호스트 facts push와 분리, `hosts: localhost`, Prism Central 여러 대를
  `nutanix_instances`로 순회, hostname 매칭).
- Credential: `cmdb_api_key` 재사용 가능. Nutanix 인증은 서비스 계정 API 키(`api_key`,
  `X-Ntnx-Api-Key` 헤더) 권장 - 없으면 username/password로 Basic 인증도 가능하지만 마찬가지로
  평문 Extra Variables 대신 Vault-encrypted 변수로 주입할 것.
- Extra Variables 예시:
  ```yaml
  cmdb_base_url: http://cmdb.internal:8000
  cmdb_validate_certs: true
  nutanix_instances:
    - name: pc01.corp.local
      base_url: https://pc01.corp.local:9440
      api_key: "{{ vault_nutanix_pc01_api_key }}"
  ```
- vCenter 쪽과 같은 이유로 `clustermgmt` 네임스페이스에서 물리 호스트(AHV 노드) 목록을,
  `vmm` 네임스페이스에서 VM 목록을 따로 조회해 `hosts`/`vms` 두 배열로 push한다 - 각 VM은
  자기 `host` 참조(`ext_id`)로 어느 물리 호스트에 속하는지 표시.
- **반입 전 확인 필요**: 호스트 목록 엔드포인트 경로와 VM의 호스트 참조 필드는 Nutanix v4
  API의 일반적인 네이밍 관례를 따른 추정이라 실제 버전으로 검증되지 않았다 - name/uuid
  (`ext_id`)/power_state만 구조화하고 호스트 하드웨어 스펙·vCPU/메모리/IP/디스크·NIC은 객체
  전체를 `extra`에 그대로 보관한다. 실제 Prism Central 응답을
  `https://developers.nutanix.com/api-reference`로 확인한 뒤
  `push_nutanix_systems_instance_tasks.yml`의 필드 매핑을 넓히면 된다.

### 8. 경유 서버(방화벽으로 직접 접속이 막혀 있을 때)

vCenter/Nutanix 시스템 정보 push 플레이북(위 6/7번)은 기본적으로 AWX 실행환경(EE) 안에서
`hosts: localhost`로 실행되면서 vCenter/Nutanix API와 CMDB에 직접 접속한다. AWX EE에서
그쪽으로 나가는 아웃바운드가 방화벽에 막혀 있고, 그 경로가 열린 특정 서버가 따로 있다면
그 서버를 경유시킬 수 있다.

- **설정 방법**: 그 서버를 AWX 인벤토리에 등록하고(다른 관리 대상 호스트와 동일하게), Job
  Template의 Extra Variables에 `systems_collector_host: <그 서버의 inventory_hostname 또는
  그룹명>`을 추가하면 된다. 플레이북 자체는 이미 이 변수를 지원하도록 돼 있음(`hosts: "{{
  systems_collector_host | default('localhost') }}"`) - 별도 수정 불필요.
- **그 서버에 실제로 필요한 것**: Python 3뿐이다. vCenter/Nutanix API 호출과 CMDB로의 최종
  POST 전부 `ansible.builtin.uri`(ansible-core 내장 모듈)로 처리하는데, 이 모듈은 curl을
  셸아웃해서 부르는 게 아니라 Python 표준 라이브러리(`urllib`)로 직접 HTTP 요청을 만든다 -
  즉 curl도 `requests` 같은 별도 pip 패키지도 필요 없다.
- **그 외 확인할 것**:
  - 그 서버에서 vCenter/Nutanix API와 CMDB(`cmdb_base_url`) 양쪽으로 아웃바운드(보통 443)가
    열려 있어야 한다 - 애초에 경유시키는 목적이므로 방화벽 규칙을 이 서버 기준으로 다시 확인.
  - `validate_certs: true`(기본값)인데 vCenter/Nutanix/CMDB 인증서가 사내 CA로 서명돼
    있다면, 그 서버의 OS 인증서 신뢰 저장소에 사내 루트 CA가 등록돼 있어야 한다(Python
    `ssl` 모듈이 OS 신뢰 저장소를 그대로 씀). 안 돼 있으면 인증서 검증 에러로 실패한다 -
    사내 CA를 등록하거나, 급하면 `cmdb_validate_certs`/각 인스턴스의 `validate_certs`를
    `false`로 우회할 수 있다(보안상 권장하지 않음, 사내 CA 등록이 정공법).
  - 그 서버의 기본 `python3` 경로가 표준이 아니면(AIX 사례처럼) 인벤토리 변수로
    `ansible_python_interpreter`를 지정할 것 - `OS_SPECS.md` 참고, facts push의 2번 항목과
    동일한 패턴.
- **주의**: `hosts: localhost`를 그냥 다른 호스트명으로 바꾸는 것만으로는 충분하지 않다 -
  원래 플레이북엔 `connection: local`이 같이 박혀 있어서, `hosts:`만 바꾸면 `connection:
  local`이 우선해 여전히 AWX EE 안에서 로컬로 실행된다(경유가 전혀 안 됨). 지금 플레이북은
  이 함정을 피하려고 `connection: local`을 아예 안 쓰고, `hosts:`가 암묵적 `localhost`일 때
  Ansible이 자동으로 로컬 실행하는 동작에 의존한다 - `systems_collector_host`로 실제
  호스트를 지정하면 자동으로 SSH 연결로 바뀐다.

### 9. 로컬 테스트

CMDB를 로컬 Docker Compose로 띄운 상태에서, 임의 값으로 API를 직접 호출해 CMDB 쪽 동작을
먼저 검증하고 싶다면 CMDB 리포지토리의 `LOCAL_ACCESS.md`를 참고 (facts/webconfig push API 섹션).
