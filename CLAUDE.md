# CMDB 프로젝트
Django + DRF 기반 CMDB. 자산 데이터는 AWX, vCenter, Nutanix Prism Central 3개 소스에서 수집.

# 환경
- 로컬 개발: Docker Compose + PostgreSQL
- 운영(폐쇄망): Kubernetes + Oracle 19c
- 로컬에서 Oracle 전용 SQL 문법 쓰지 말 것

# 수집 소스
- AWX: ansible fact → POST /api/facts/
- vCenter: pyvmomi/REST API → POST /api/vms/vcenter-sync/
- Nutanix Prism Central: REST API v3 → POST /api/vms/nutanix-sync/

# 배포
- 이미지는 Harbor로 push 후 K8s Deployment
- NodePort 방식 서비스 노출