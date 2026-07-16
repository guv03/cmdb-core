# cmdb-core Helm 차트

CMDB(Django + DRF)를 폐쇄망 K8s에 배포하는 차트. Harbor에 push한 이미지를 NodePort
서비스로 노출한다.

## 사전 준비

1. 이미지를 빌드해서 Harbor로 push:
   ```powershell
   docker build -t harbor.internal/cmdb/cmdb-core:1.0.0 .
   docker push harbor.internal/cmdb/cmdb-core:1.0.0
   ```
2. Oracle 19c 접속 정보(호스트/포트/서비스명/계정) 준비.
3. `DJANGO_SECRET_KEY`, DB 비밀번호, `AWX_API_KEY` — 세 값은 반드시 placeholder를 실제 값으로
   바꿔서 배포한다 (아래 참고).

## 설치

values 파일을 따로 만들어서 얹는 걸 권장 (민감정보를 이 리포지토리의 `values.yaml`에 직접
커밋하지 말 것):

```yaml
# values-prod.yaml (git에 커밋하지 않는 파일)
image:
  repository: harbor.internal/cmdb/cmdb-core
  tag: "1.0.0"

django:
  secretKey: "<실제 django secret key>"

database:
  engine: django.db.backends.oracle
  host: <oracle host>
  port: "1521"
  name: <oracle service name 또는 easy-connect 문자열>
  user: <oracle user>
  password: "<실제 비밀번호>"

awx:
  apiKey: "<실제 AWX API 키>"
```

```powershell
helm install cmdb helm/cmdb-core -f values-prod.yaml
```

민감정보를 Helm values 대신 별도로 관리하는 시크릿 도구(예: 사내 시크릿 오퍼레이터)를 쓴다면,
직접 만든 Secret 이름을 `existingSecret`에 지정하면 된다 (이 경우 `django.secretKey` /
`database.password` / `awx.apiKey`는 무시됨). 그 Secret에는 `DJANGO_SECRET_KEY`,
`POSTGRES_PASSWORD`, `AWX_API_KEY` 키가 있어야 한다.

## 업그레이드

```powershell
helm upgrade cmdb helm/cmdb-core -f values-prod.yaml --set image.tag=1.1.0
```

마이그레이션은 install/upgrade마다 자동으로 도는 Job(Helm hook)이 처리한다. 끄고 싶으면
`migration.enabled=false`.

## 확인

```powershell
helm install cmdb helm/cmdb-core -f values-prod.yaml --dry-run --debug   # 렌더링만 확인
helm lint helm/cmdb-core                                                 # 차트 검증
```

## 관리자 계정 생성 (최초 1회)

```powershell
kubectl exec -it deploy/cmdb-cmdb-core -- python manage.py createsuperuser
```

## AWX 쪽 설정

`../awx/README.md` 참고 — Job Template의 `cmdb_base_url`이 이 서비스의 NodePort로
접근 가능한 주소를 가리켜야 한다.
