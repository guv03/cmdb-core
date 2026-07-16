# AWX → CMDB facts push 플레이북

vCenter/Nutanix dynamic inventory로 감지된 VM에 ansible facts를 수집하고, 하이퍼바이저
메타데이터와 함께 CMDB(`POST /api/facts/`)로 push하는 플레이북. CMDB는 vCenter/Nutanix API를
직접 호출하지 않으므로 이 플레이북이 CMDB로 자산 데이터가 들어가는 유일한 경로다.

## 파일

- `push_facts_to_cmdb.yml` — 메인 플레이북. AWX Job Template에 그대로 연결해서 쓴다.
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

### 2. Job Template

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

### 3. 로컬 테스트

CMDB를 로컬 Docker Compose로 띄운 상태에서, 임의 값으로 API를 직접 호출해 CMDB 쪽 동작을
먼저 검증하고 싶다면 CMDB 리포지토리의 `LOCAL_ACCESS.md`를 참고 (facts push API 섹션).
