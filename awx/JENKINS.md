# Jenkins + Ansible 실행 환경 (AWX 대체)

내부망에서 AWX 대신 **Jenkins(스케줄·이력·자격증명) + Ansible(실행)** 으로 CMDB push 플레이북을
돌리는 구성. 플레이북 자체는 AWX 때와 동일하고, AWX가 해주던 일만 아래처럼 옮겼다.

| AWX | Jenkins + Ansible |
|---|---|
| 실행환경(EE) 이미지 | `jenkins/Dockerfile` — Jenkins LTS + ansible-core + pywinrm + 플러그인을 한 이미지로 |
| Project (GitLab 연동) | Pipeline Job의 "Pipeline script from SCM" → 내부 GitLab 플레이북 리포 |
| Job Template (플레이북 + 대상 그룹) | `Jenkinsfile`의 `PLAYBOOKS` 목록(플레이북 ↔ 인벤토리 그룹) |
| Inventory | `inventories/hosts` (기존 파일, 추가할 그룹 예시는 `inventories/hosts.example`) |
| Credential / Extra Variables | Jenkins Credentials 2개(SSH 키, extra vars 시크릿 파일) |
| Schedule | `Jenkinsfile`의 `triggers { cron(...) }` |
| Limit / Verbosity 재실행 | "Build with Parameters"의 `PLAYBOOK`/`LIMIT`/`VERBOSITY` |

## 구성

```
[전용 VM]  docker run cmdb-ansible-jenkins
   └─ Jenkins built-in 노드에서 ansible-playbook 실행
        ├─ SSH/WinRM → 관리 대상 서버들      (방화벽: 이 VM IP만 등록)
        ├─ HTTPS → vCenter / Nutanix API
        └─ HTTP(S) → CMDB API
   └─ git checkout ← 내부 GitLab(플레이북 리포)
```

- 실행은 전용 VM 한 곳에서만 일어난다. 컨테이너 트래픽은 Docker bridge NAT로 VM IP로 나가므로
  방화벽 출발지 IP가 하나로 고정된다.
- 별도 Jenkins 에이전트 없이 built-in 노드에서 실행한다(이 Jenkins는 CMDB 수집 전용).

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

## 2. 전용 VM에서 실행 (내부망)

```bash
docker load -i cmdb-ansible-jenkins-2.580.1-ac2.21.5.tar
docker volume create jenkins_home
docker run -d --name cmdb-jenkins --restart unless-stopped \
  -p 8080:8080 -v jenkins_home:/var/jenkins_home \
  cmdb-ansible-jenkins:2.580.1-ac2.21.5
docker logs cmdb-jenkins   # 초기 관리자 비밀번호 확인
```

- 최초 설정 마법사에서 플러그인 설치 단계는 건너뛴다(이미 이미지에 포함, 폐쇄망이라 다운로드도 불가).
- 이미지 교체 시 `jenkins_home` 볼륨은 그대로 두고 컨테이너만 새 이미지로 다시 띄우면 Job/이력/Credential이 유지된다.
- RHEL 계열 VM이면 docker 대신 podman도 같은 명령으로 동작한다(OS 기본 repo라 설치가 더 쉬움).

## 3. 플레이북 리포 (내부 GitLab `dt/ansible`)

AWX 때 쓰던 리포를 그대로 쓴다. 레이아웃:

```
dt/ansible
├─ Jenkinsfile          ← 추가 (이 디렉토리의 Jenkinsfile)
├─ ansible.cfg          ← 추가 (inventory = inventories/hosts)
├─ inventories/hosts    ← 기존 인벤토리
└─ playbooks/           ← 기존 플레이북 (facts는 push_fact_to_cmdb.yml)
```

- `Jenkinsfile`/`ansible.cfg`만 리포 루트에 추가하면 된다. `jenkins/`(이미지 빌드용)는 외부망에서만 쓰므로 GitLab에 안 올려도 됨.
- 기존 `inventories/hosts`는 그룹 없는 평면 목록이다(AWX 때는 Job Template별로 대상을 안 나눔). 그대로 두면
  **facts/processes만 전체 호스트 대상으로 실행되고, 설정 수집(WebToB/Apache/Nginx/Oracle/JEUS/Tomcat)은
  대상 그룹이 없어 자동으로 건너뛴다.** 설정 수집을 돌리려면 `[webtob]`/`[jeus_admin]`/`[oracle]` 같은 그룹을
  파일 아래쪽에 추가해 해당 호스트 이름만 나열하면 된다 — `inventories/hosts.example` 참고. 그룹 이름은
  `Jenkinsfile`의 `PLAYBOOKS` `limit`과 맞물려 있다.
- Windows 호스트가 있으면 `[windows]` 그룹은 꼭 만들 것 — WinRM 연결 변수를 거기 두고, processes(`ps -ef`)
  수집 대상에서도 이 그룹으로 제외된다.
- 서버별 경로/계정 변수(`webtob_config_path`, `oracle_home`, `jeus6_instance_name` 등)는 AWX 때와
  동일하게 인벤토리 호스트/그룹 변수로 둔다 — 각 플레이북 상단 주석과 `README.md` 참고.

## 4. Jenkins 설정

### Credentials (Manage Jenkins → Credentials)

| ID | 종류 | 내용 |
|---|---|---|
| `cmdb-ansible-ssh` | SSH Username with private key | 관리 대상 서버 접속 계정/키 (AWX Machine Credential에 해당) |
| `cmdb-ansible-extra-vars` | Secret file | `jenkins/extra_vars.example.yml` 형식의 YAML — `cmdb_api_key`, vCenter/Nutanix 계정, `vault_*` 비밀번호 |
| (GitLab 접근용) | Username with password(토큰) | 플레이북 리포 checkout용 |

- 시크릿은 Jenkins Credentials에만 둔다 — GitLab과 외부망 리포 어디에도 실제 값을 커밋하지 않는다.

### SSH 키 (root 접속)

1. Jenkins VM에서 키 생성: `ssh-keygen -t ed25519 -C cmdb-ansible -f ./cmdb-ansible -N ""`
   (ed25519 미지원 구버전 OpenSSH 서버가 섞여 있으면 `-t rsa -b 4096`)
2. 개인키(`cmdb-ansible`)를 `cmdb-ansible-ssh` Credential(Username: `root`)에 붙여넣고, VM의 개인키 파일은 삭제.
3. 공개키는 서버마다 root 비밀번호가 달라 일괄 배포하지 않고, 각 서버 `/root/.ssh/authorized_keys`에
   아래 한 줄을 직접(또는 서버 담당자가) 추가한다 — `from=`으로 Jenkins VM IP에서만 이 키를 쓸 수 있게 제한:
   ```
   from="<Jenkins VM IP>" ssh-ed25519 AAAA... cmdb-ansible
   ```
   권한은 `.ssh` 700, `authorized_keys` 600. sshd의 `PermitRootLogin`이 `no`면 키 접속도 막히므로
   `prohibit-password`(구버전은 `without-password`)여야 한다.
- `become`(webtob/oracle 계정 전환)에 sudo 비밀번호가 필요하면 `ansible_become_password: "{{ vault_become_password }}"`를
  인벤토리에 두고 값은 extra vars 시크릿 파일에 넣는다.

### Pipeline Job

1. New Item → Pipeline (예: `cmdb-collect`)
2. Pipeline → Definition: "Pipeline script from SCM", SCM: Git, 내부 GitLab 리포 URL + 위 GitLab Credential,
   Script Path: `Jenkinsfile`
3. 최초 1회 "Build Now"로 실행하면 `Jenkinsfile`의 파라미터/스케줄이 Job에 등록된다.

### 테스트 (정기 실행 켜기 전)

`Jenkinsfile`의 `triggers`(정기 실행)는 처음엔 주석 처리돼 있고, `PLAYBOOK` 기본값은 `NONE`(아무것도 안 함)이다 —
Job 최초 등록 빌드나 실수로 누른 "Build"가 전체 실행이 되지 않게 하기 위함. 플레이북 하나·서버 하나씩 확인한다:

1. "Build with Parameters" → `PLAYBOOK=facts`, `LIMIT=<서버 1대>`, `VERBOSITY=-v`
2. Jenkins 콘솔 로그에서 성공 확인 → CMDB 대시보드에서 그 자산의 "최근 반영일"이 갱신됐는지 확인
3. 같은 플레이북을 `LIMIT` 없이(전체 대상) 실행
4. 다음 플레이북(webtob, jeus ...)도 1~3 반복 — 단, 인벤토리에 해당 그룹을 먼저 추가해야 대상이 생긴다
5. 전부 확인되면 `triggers` 주석을 풀어 GitLab에 push → 다음 날부터 정기 실행

### 실행 방식

- **정기 실행**: 매일 새벽(`cron('H 2 * * *')`) — `PLAYBOOK` 선택값과 무관하게 항상 `ALL` — facts → processes → WebToB/Apache/Nginx →
  Oracle → JEUS/JEUS6/Tomcat 순서. 한 단계가 실패해도 나머지 단계는 계속 실행되고 빌드는 실패로 표시된다.
  인벤토리 그룹이 비어있는 단계는 자동으로 건너뛴다.
- **vCenter/Nutanix**: 연동 준비 전엔 ALL에 포함되지 않는다(`INCLUDE_SYSTEMS=false`). 준비되면 기본값을
  바꾸거나 `PLAYBOOK=vcenter`로 단독 실행.
- **재실행/디버깅**: "Build with Parameters"에서 `PLAYBOOK=webtob`, `LIMIT=drnrap01`, `VERBOSITY=-vvv`처럼
  지정 — AWX의 Limit/Verbosity와 같다. `LIMIT`은 각 플레이북의 대상 그룹과 교집합으로 적용된다.
