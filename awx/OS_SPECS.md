# AWX 대상 OS별 스펙

AWX가 관리하는 서버들의 OS별 기본 환경(Python/PowerShell 버전 등) 정보를 기록한다 — 같은 OS면
대체로 같은 특성을 보이므로 호스트 단위가 아니라 **OS 단위**로 정리한다. 전수조사 문서가
아니라 트러블슈팅하면서 알게 되는 값을 그때그때 채워나가는 문서. 값은 `WORKLOG.md`의 해당
날짜 항목에 더 자세한 진단 과정이 남아있다.

## Unix 계열(AIX / Linux) — Python 버전 요구사항

`push_nginx_config_to_cmdb.yml` 첫 실행에서 발견(2026-07-29) — 대상 노드의 Python 버전이
낮으면 `ansible.builtin.slurp` 같은 코어 모듈조차 `SyntaxError: future feature annotations
is not defined`로 실패한다(현재 AWX의 ansible-core 버전이 `module_utils` 코드에 3.8+ 문법을
쓰기 때문, 커스텀 플레이북 로직과 무관 — 어떤 모듈을 돌려도 동일하게 실패). AIX와 Linux는
둘 다 Ansible이 SSH+Python으로 접속하는 동일한 방식이라 요구사항도 동일하게 취급.

- **3.6.x / 3.7.x: 실패 확인됨**
- **최소 3.8 이상 필요, 3.9 권장**

기본 Python이 낮은 호스트는 (1) 이미 다른 경로에 신버전 Python이 설치돼 있으면 인벤토리
`ansible_python_interpreter`로 그 경로를 지정하거나, (2) 없으면 Python 3.9를 별도 설치해야
한다.

| OS | 기본 Python 3 | AWX 호환 | 비고 |
|---|---|---|---|
| (미상) | 3.6.x | ✕ 실패 확인 | POPSAP01(nginx)에서 발견 — 업그레이드 필요, 아직 미조치 |
| (미상) | 3.9.x | ✓ 정상 | 어떤 OS인지 추가 확인 필요 |
| AIX | (미확인) | (미확인) | 아직 실제로 push해본 적 없음 — Linux와 동일 취급하되(SSH+Python 방식) 실제 기본 Python 버전은 서버별 확인 필요 |

## Windows — Python이 아니라 PowerShell 기반(개념이 다름)

**Windows는 Python 버전이라는 개념 자체가 없다.** Ansible이 Windows 대상 노드를 관리할 때는
Python이 아니라 **PowerShell**로 모듈을 실행한다(연결 방식은 WinRM, 또는 ansible-core
2.18부터 정식 지원되는 SSH). 그래서 AIX/Linux처럼 "Python 몇 버전 이상"을 요구하는 게 아니라
아래 조건이 필요하다.

- **OS**: Windows Server 2016 / Windows 10 이상(이보다 오래된 Windows는 PowerShell을 별도
  업그레이드해야 함)
- **PowerShell**: 5.1 이상 — 위 OS 버전은 기본 설치 상태로 이미 PowerShell 5.1을 포함하고
  있어 별도 설치 불필요한 경우가 많음
- **.NET Framework**: 버전 요구사항이 ansible-core 버전마다 조금씩 다르게 언급돼서(4.0~4.7.2
  등 출처마다 표기가 다름) 여기 확정 수치를 적진 않음 — 실제 설치 전에 대상 Windows
  버전 기준으로 공식 문서(`Setting up a Windows Host`) 재확인 권장
- **연결 설정**: WinRM 리스너 활성화 필요(`ConfigureRemotingForAnsible.ps1` 스크립트로 자동화
  가능) — 또는 SSH 방식(ansible-core 2.18+)이면 Win32-OpenSSH 설치로 대체 가능
- 이 프로젝트에서 아직 Windows 대상으로 실제 push해본 적 없음(WebToB는 Windows/Linux/AIX
  전부 대상이라고 CLAUDE.md에 명시돼 있지만, 지금까지 실제 트러블슈팅은 Linux만 있었음)

## 참고 자료

- [Managing Windows hosts with Ansible](https://docs.ansible.com/projects/ansible/latest/os_guide/intro_windows.html)
- [Setting up a Windows Host](https://docs.ansible.com/projects/ansible/9/os_guide/windows_setup.html)

<!-- 새 OS/재확인 결과는 표에 행 추가. Windows를 실제로 붙이게 되면 위 .NET/PowerShell 수치를 실측값으로 교체할 것. -->
