# Jenkins + Ansible 실행 환경 (AWX 대체)

내부망에서 AWX 대신 **Jenkins(스케줄·이력·자격증명) + Ansible(실행)** 으로 CMDB push 플레이북을
돌리는 구성. 플레이북 자체는 AWX 때와 동일하고, AWX가 해주던 일만 아래처럼 옮겼다.

| AWX | Jenkins + Ansible |
|---|---|
| 실행환경(EE) 이미지 | `jenkins/Dockerfile` — Jenkins LTS + ansible-core + 플러그인을 한 이미지로 |
| Project (GitLab 연동) | Pipeline Job의 "Pipeline script from SCM" → 내부 GitLab 플레이북 리포 |
| Job Template (플레이북 + 대상 그룹) | `Jenkinsfile`의 `PLAYBOOKS` 목록(플레이북 ↔ 인벤토리 그룹) |
| Inventory | `inventories/hosts` (기존 파일, 추가할 그룹 예시는 `inventories/hosts.example`) |
| Credential / Extra Variables | Jenkins Credentials 2개(SSH 키, extra vars 시크릿 파일) |
| Schedule | `Jenkinsfile`의 `triggers { cron(...) }` |
| Limit / Verbosity 재실행 | "Build with Parameters"의 `PLAYBOOK`/`LIMIT`/`VERBOSITY` |

## 구성

```
[K8s] Jenkins Pod (ansible 내장 이미지, built-in 노드에서 ansible-playbook 실행)
   ├─ SSH 22 → 관리 대상 서버들(Linux/AIX/Windows 전부 SSH)   방화벽·from= 에는 K8s 워커 노드 IP들 등록
   └─ HTTPS → vCenter(443) / Nutanix Prism Central(9440) API → CMDB API로 push

관리 대상 서버들 → CMDB API (facts/설정 push는 AWX 때와 동일하게 각 서버에서 CMDB로 직접)
Jenkins Pod ← git checkout ← 내부 GitLab(플레이북 리포)
```

- **서버 내부 수집(facts/webtob/jeus 등)**: Jenkins Pod에서 각 서버로 직접 SSH 접속한다. Pod는 재시작 시 다른
  노드에 뜰 수 있으므로 대상 서버의 방화벽과 `authorized_keys`의 `from=`에는 **K8s 워커 노드 IP 전부**를 등록한다.
- **vCenter/Nutanix 수집**: 서버에 SSH로 붙지 않고 Pod 안(localhost)에서 API를 호출해 결과를 Pod가 CMDB로 보낸다 —
  Pod → vCenter/Nutanix, Pod → CMDB 경로가 열려 있어야 한다.
- 방화벽 때문에 직접 접속이 어려우면 특정 서버를 경유하게 바꿀 수 있다 — 아래 "3. 콜렉터 서버 경유(선택)".

## 1. 이미지 빌드 (외부망)

```bash
cd awx/jenkins
docker build -t cmdb-ansible-jenkins:2.580.1-ac2.21.5 \
  --build-arg JENKINS_IMAGE=jenkins/jenkins:2.580.1-lts-jdk21 .
docker save cmdb-ansible-jenkins:2.580.1-ac2.21.5 -o cmdb-ansible-jenkins-2.580.1-ac2.21.5.tar
```

- 태그는 `<Jenkins LTS>-ac<ansible-core>` 형식. CMDB 이미지(`VERSION`)와 별개로 관리한다.
- Jenkins 플러그인(`plugins.txt`)은 빌드 시점 최신 호환 버전이 이미지 안에 고정된다 — 폐쇄망
  Jenkins에서 플러그인 업데이트/설치는 안 되므로, 필요한 플러그인은 반드시 여기 추가해 다시 빌드.
- Python 패키지/collection을 추가하면 `requirements.txt`/`requirements.yml` 수정 후 다시 빌드.
  플레이북만 바뀐 경우엔 이미지 재빌드가 필요 없다(GitLab push만).

## 2. K8s 배포 (내부망)

1. 이미지를 Harbor에 push(CMDB 이미지와 같은 절차):
   ```bash
   docker load -i cmdb-ansible-jenkins-2.580.1-ac2.21.5.tar
   docker tag cmdb-ansible-jenkins:2.580.1-ac2.21.5 <harbor>/<project>/cmdb-ansible-jenkins:2.580.1-ac2.21.5
   docker push <harbor>/<project>/cmdb-ansible-jenkins:2.580.1-ac2.21.5
   ```
2. `jenkins/k8s/jenkins.yaml`의 `CHANGE_ME`(Harbor 이미지 경로)를 채우고 적용 — StorageClass는 내부망 기존 `nfs-csi`(AWX/Harbor와 동일)로 지정돼 있음:
   ```bash
   kubectl get storageclass              # 쓸 수 있는 StorageClass 이름 확인 ((default) 표시가 기본값)
   kubectl apply -f jenkins.yaml
   kubectl -n cmdb-jenkins get pod,svc   # Pod Running + NodePort 번호 확인
   kubectl -n cmdb-jenkins logs deploy/cmdb-jenkins   # 초기 관리자 비밀번호
   ```
3. `http://<아무 워커 노드 IP>:<NodePort>`로 접속. 최초 설정 마법사의 플러그인 설치 단계는 건너뛴다
   (이미 이미지에 포함, 폐쇄망이라 다운로드도 불가).

- 이미지 교체는 매니페스트의 이미지 태그만 바꿔 다시 apply — PVC(`jenkins_home`)는 그대로라 Job/이력/Credential 유지.
- PVC 권한 오류(`Permission denied: /var/jenkins_home`)가 나면 NFS 등에서 `fsGroup`이 안 먹는 경우 —
  스토리지 쪽 디렉토리 소유자를 uid 1000으로 맞춘다.

## 3. 콜렉터 서버 경유 (선택)

기본 구성(Pod에서 직접 접속)으로 방화벽을 열기 어려울 때만 쓴다. 전체 서버에 접근 가능한 서버 하나를 두고
모든 SSH 접속을 그 서버를 거쳐 보낸다(SSH ProxyCommand - 그 서버는 TCP만 중계하므로 개인키·ansible 설치 불필요).

- `Jenkinsfile`의 `CMDB_COLLECTOR = 'root@<콜렉터 주소>'`로 켠다(비우면 직접 접속).
- 콜렉터 sshd에 `AllowTcpForwarding local`(또는 `yes`) 필요 — `no`면 콜렉터 `/var/log/secure`에
  `refused local port forward`가 찍히며 실패한다.
- `authorized_keys`의 `from=`: 대상 서버는 `<콜렉터 IP>`, 콜렉터 자신은 `<K8s 워커 노드 IP들>,<콜렉터 IP>`
  (콜렉터 자신도 수집 대상이면 콜렉터→콜렉터 접속이 생겨 자기 IP가 필요).
- vCenter/Nutanix API 호출도 콜렉터에서 하려면 인벤토리 `[collector]` 그룹 + extra vars의
  `systems_collector_host: collector`(콜렉터에 Python 3 필요).

## 4. 플레이북 리포 (내부 GitLab `dt/ansible`)

AWX 때 쓰던 리포를 그대로 쓴다. 레이아웃:

```
dt/ansible
├─ Jenkinsfile          ← 추가 (이 디렉토리의 Jenkinsfile, CMDB_COLLECTOR 값 수정)
├─ ansible.cfg          ← 추가 (inventory = inventories/hosts)
├─ inventories/hosts    ← 기존 인벤토리 (+ [collector]/[windows] 등 그룹 추가)
└─ playbooks/           ← 기존 플레이북 (facts는 push_fact_to_cmdb.yml)
```

- `Jenkinsfile`/`ansible.cfg`만 리포 루트에 추가하면 된다. `jenkins/`(이미지 빌드·K8s 매니페스트)는 GitLab에 안 올려도 됨.
- 기존 `inventories/hosts`는 그룹 없는 평면 목록이다(AWX 때는 Job Template별로 대상을 안 나눔). 그대로 두면
  **facts/processes만 전체 호스트 대상으로 실행되고, 설정 수집(WebToB/Apache/Nginx/Oracle/JEUS/Tomcat)은
  대상 그룹이 없어 자동으로 건너뛴다.** 설정 수집을 돌리려면 `[webtob]`/`[jeus_admin]`/`[oracle]` 같은 그룹을
  파일 아래쪽에 추가해 해당 호스트 이름만 나열하면 된다 — `inventories/hosts.example` 참고. 그룹 이름은
  `Jenkinsfile`의 `PLAYBOOKS` `limit`과 맞물려 있다.
- Windows 호스트가 있으면 `[windows]` 그룹은 꼭 만들 것 — SSH+PowerShell 접속 변수(`ansible_shell_type=powershell`)를
  거기 두고, processes(`ps -ef`) 수집 대상에서도 이 그룹으로 제외된다.
- 서버별 경로/계정 변수(`webtob_config_path`, `oracle_home`, `jeus6_instance_name` 등)는 AWX 때와
  동일하게 인벤토리 호스트/그룹 변수로 둔다 — 각 플레이북 상단 주석과 `README.md` 참고.

## 5. Jenkins 설정

### Credentials (Manage Jenkins → Credentials)

| ID | 종류 | 내용 |
|---|---|---|
| `cmdb-ansible-ssh` | SSH Username with private key | 관리 대상 서버 공용 접속 키 (Username: `root`) |
| `cmdb-ansible-extra-vars` | Secret file | `jenkins/extra_vars.example.yml` 형식의 YAML — `cmdb_base_url`, `cmdb_api_key`, vCenter/Nutanix 접속 정보(`vcenter_instances`/`nutanix_instances`) |
| (GitLab 접근용) | Username with password(토큰) | 플레이북 리포 checkout용 |

- 시크릿은 Jenkins Credentials에만 둔다 — GitLab과 외부망 리포 어디에도 실제 값을 커밋하지 않는다.
- `cmdb_api_key`는 CMDB에 설정된 값(Helm values의 `awx.apiKey` / Secret의 `AWX_API_KEY`)과 같아야 한다.

### SSH 키 (root 접속)

1. 키 생성(아무 Linux에서): `ssh-keygen -t ed25519 -C cmdb-ansible -f ./cmdb-ansible -N ""`
   (ed25519 미지원 구버전 OpenSSH 서버가 섞여 있으면 `-t rsa -b 4096`)
2. 개인키(`cmdb-ansible`)를 `cmdb-ansible-ssh` Credential(Username: `root`)에 붙여넣고, 생성한 개인키 파일은 삭제.
3. 공개키는 서버마다 root 비밀번호가 달라 일괄 배포하지 않고 직접(또는 서버 담당자가) 등록한다.
   Pod에서 직접 접속하므로 출발지는 K8s 워커 노드 IP다(`kubectl get nodes -o wide`의 INTERNAL-IP 전부):
   - **Linux/AIX** `/root/.ssh/authorized_keys`: `from="<워커 노드 IP들, 콤마 구분>" ssh-ed25519 AAAA... cmdb-ansible`
   - **Windows**(Administrator): `C:\ProgramData\ssh\administrators_authorized_keys`에 같은 줄
   - 콜렉터 경유를 쓰면 `from=` 값이 달라진다 — 위 "3. 콜렉터 서버 경유(선택)" 참고.
   - 권한은 `.ssh` 700, `authorized_keys` 600. sshd의 `PermitRootLogin`이 `no`면 키 접속도 막히므로
     `prohibit-password`(구버전은 `without-password`)여야 한다.

### Pipeline Job

1. New Item → Pipeline (예: `cmdb-collect`)
2. Pipeline → Definition: "Pipeline script from SCM", SCM: Git, 내부 GitLab 리포 URL + 위 GitLab Credential,
   Script Path: `Jenkinsfile`
3. 최초 1회 "Build Now"로 실행하면 `Jenkinsfile`의 파라미터/스케줄이 Job에 등록된다(기본값 `NONE`이라 실제 실행은 없음).

### 테스트 (정기 실행 켜기 전)

`Jenkinsfile`의 `triggers`(정기 실행)는 처음엔 주석 처리돼 있고, `PLAYBOOK` 기본값은 `NONE`(아무것도 안 함)이다 —
Job 최초 등록 빌드나 실수로 누른 "Build"가 전체 실행이 되지 않게 하기 위함. 플레이북 하나·서버 하나씩 확인한다:

1. "Build with Parameters" → `PLAYBOOK=facts`, `LIMIT=<서버 1대>`, `VERBOSITY=-v`
2. Jenkins 콘솔 로그에서 성공 확인 → CMDB 대시보드에서 그 자산의 "최근 반영일"이 갱신됐는지 확인
3. 같은 플레이북을 `LIMIT` 없이(전체 대상) 실행
4. 다음 플레이북(webtob, jeus ...)도 1~3 반복 — 단, 인벤토리에 해당 그룹을 먼저 추가해야 대상이 생긴다
5. 전부 확인되면 `triggers` 주석을 풀어 GitLab에 push → 다음 날부터 정기 실행

접속이 안 되면 `VERBOSITY=-vvv`로 다시 실행해 SSH 단계를 보고, 대상 서버 `/var/log/secure`에서 실제 출발지 IP와
거부 사유(`from=` 불일치/`PermitRootLogin`/키 불일치)를 확인한다.

### 실행 방식

- **정기 실행**: 매일 새벽(`cron('H 2 * * *')`) — `PLAYBOOK` 선택값과 무관하게 항상 `ALL` — facts → processes → WebToB/Apache/Nginx →
  Oracle → JEUS/JEUS6/Tomcat 순서. 한 단계가 실패해도 나머지 단계는 계속 실행되고 빌드는 실패로 표시된다.
  인벤토리 그룹이 비어있는 단계는 자동으로 건너뛴다.
- **vCenter/Nutanix**: 연동 준비 전엔 ALL에 포함되지 않는다(`INCLUDE_SYSTEMS=false`). 준비되면 기본값을
  바꾸거나 `PLAYBOOK=vcenter`로 단독 실행.
- **재실행/디버깅**: "Build with Parameters"에서 `PLAYBOOK=webtob`, `LIMIT=drnrap01`, `VERBOSITY=-vvv`처럼
  지정 — AWX의 Limit/Verbosity와 같다. `LIMIT`은 각 플레이북의 대상 그룹과 교집합으로 적용된다.
