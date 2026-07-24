# 샘플 facts 데이터

AWX push 페이로드(`POST /api/facts/`) 형식의 샘플 데이터. 동적 필드 등록 후 실제 push 흐름으로 검증할 때 재사용한다.

- `drnrap01.json`: RHEL 9.4 / Nutanix AHV 게스트 실제 ansible facts 샘플(호스트명 `DRNRAP01`)

## 사용법

로컬 Docker Compose로 기동된 상태에서 실행 (`AWX_API_KEY`는 `.env` 값과 일치해야 함):

```bash
curl -X POST http://localhost:8000/api/facts/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AWX_API_KEY" \
  --data @samples/facts/drnrap01.json
```
