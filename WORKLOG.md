# 작업 일지

일 단위로 진행한 작업을 기록한다. 새 날짜는 위에 추가한다.

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
