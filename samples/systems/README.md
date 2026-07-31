# 샘플 systems 데이터

`POST /api/systems/`(vCenter/Nutanix VM 인벤토리 push) 페이로드 형식의 샘플 데이터.
`drnrap01`처럼 이미 facts push로 등록된 자산과 같은 hostname을 써야 매칭이 확인된다
(`samples/facts/drnrap01.json` 먼저 push해서 자산을 등록해둘 것).

- `nutanix_example.json`: Nutanix 형태 샘플(hostname `drnrap01`로 기존 자산과 매칭됨)

## 사용법

로컬 Docker Compose로 기동된 상태에서 실행 (`AWX_API_KEY`는 `.env` 값과 일치해야 함):

```bash
curl -X POST http://localhost:8000/api/systems/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AWX_API_KEY" \
  --data @samples/systems/nutanix_example.json
```
