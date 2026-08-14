# 샘플 DB(Oracle) 데이터

`POST /api/database/`(DB 설정 push) 페이로드 형식의 샘플 데이터. `content`는
`awx/push_oracle_config_to_cmdb.yml`이 실제로 sqlplus에서 뽑아낼 것으로 기대하는 JSON
문자열을 손으로 흉내 낸 것이다 - 이 저장소 개발 환경에는 실제 Oracle 인스턴스가 없어
CMDB 쪽(파싱/저장/대시보드/엑셀) 검증은 이 합성 데이터로 마쳤지만, **AWX 플레이북의 SQL
자체(특히 `listener_port` 추출용 정규식)는 실제 Oracle 12c/19c 환경에서 아직 실측 검증되지
않았다** - 처음 반입할 때 실제 sqlplus 출력을 확인하고 필요하면 SQL을 조정할 것.

- `oracle_standalone_19c.json`: Standalone 19c 샘플(hostname `drnrap01`로 기존 자산과 매칭됨, 인스턴스 1개)
- `oracle_rac_12c.json`: RAC 12c 샘플(hostname `ddorap01`/`iawxap01`로 기존 자산과 매칭됨, 인스턴스 2개 - `collected_from_instance`가 `racdb1`이라 소스의 asset은 `ddorap01`로 잡힘)

## 사용법

로컬 Docker Compose로 기동된 상태에서 실행 (`AWX_API_KEY`는 `.env` 값과 일치해야 함,
`samples/facts/`로 위 hostname의 자산이 먼저 등록돼 있어야 매칭이 확인된다):

```bash
curl -X POST http://localhost:8000/api/database/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AWX_API_KEY" \
  --data @samples/oracle/oracle_standalone_19c.json

curl -X POST http://localhost:8000/api/database/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AWX_API_KEY" \
  --data @samples/oracle/oracle_rac_12c.json
```

## 새 필드를 추가하고 싶을 때(코드 수정 없이)

`content`의 최상위 JSON(instances 배열 제외)은 `DbConfigSource.extra`에 그대로 보관된다.
`force_logging`/`flashback_on`/`cdb`/`supplemental_log_data_min`처럼 고정 컬럼으로 승격
안 된 값도 이미 `extra`에 들어있으므로, admin의 **Db config source field definitions**에서
`key`(예: `force_logging`)와 `label`만 등록하면 다음 push부터(또는 "선택한 필드 소급 백필
실행" 액션으로 이미 push된 DB에도 즉시) 대시보드 DB 목록/엑셀 다운로드에 컬럼으로 나타난다
- OS(facts)/시스템(vCenter·Nutanix) 목록과 완전히 동일한 방식이다.
