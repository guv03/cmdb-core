# 운영(폐쇄망) 배포 가이드

CMDB를 외부망에서 빌드해 폐쇄망 K8s로 반입하고 Helm으로 배포하는 절차. 로컬 개발 환경은
[LOCAL_ACCESS.md](LOCAL_ACCESS.md), 차트 자체의 옵션 상세는
[helm/cmdb-core/README.md](helm/cmdb-core/README.md), AWX 연동은
[awx/README.md](awx/README.md) 참고.

## 사전 준비물

- 외부망: Docker, Harbor 계정(push 권한)
- 폐쇄망: Harbor 접근 가능한 K8s 클러스터, `kubectl`/`helm` 사용 가능한 환경
- Oracle 19c 접속 정보: host, port, service name(또는 easy-connect 문자열), 계정/비밀번호
  (CMDB 전용 스키마·계정은 DBA에게 미리 요청해서 준비)

## 1. 외부망: 이미지 빌드

의존성은 이미 `vendor/wheels/`에 오프라인 설치용으로 전부 들어있어서(Django, DRF, psycopg,
oracledb, gunicorn, whitenoise 등) 빌드 시점에 외부 pip 저장소 접근이 필요 없다. 즉 이미지
자체가 빌드되고 나면 완전히 오프라인으로 기동 가능하다.

```powershell
docker build -t cmdb-core:1.0.0 .
```

빌드에 새 파이썬 패키지가 필요해졌다면, `requirements.txt`에 추가하기 전에 반드시
`vendor/wheels/`에 해당 wheel(및 전이 의존성)을 먼저 받아둬야 한다:

```powershell
pip download --only-binary=:all: --platform manylinux2014_x86_64 --python-version 313 `
  --implementation cp -d vendor/wheels <패키지명>
```

## 2. 이미지를 폐쇄망으로 반입

Harbor를 외부망에서 직접 push할 수 없는 구조라면 이미지를 파일로 내보내서 반입한다:

```powershell
docker save cmdb-core:1.0.0 -o cmdb-core-1.0.0.tar
# cmdb-core-1.0.0.tar 를 폐쇄망 반입 절차(사내 규정)에 따라 이동
```

폐쇄망 쪽에서:

```powershell
docker load -i cmdb-core-1.0.0.tar
docker tag cmdb-core:1.0.0 harbor.internal/cmdb/cmdb-core:1.0.0
docker push harbor.internal/cmdb/cmdb-core:1.0.0
```

(외부망에서 Harbor로 바로 push 가능한 네트워크 구조라면 `docker save`/`load` 없이 build 후
바로 `docker push`.)

## 3. Oracle 준비 확인

CMDB 전용 계정/스키마가 이미 만들어져 있는지, 아래 값들을 알고 있는지 확인:

- host, port(기본 1521), service name 또는 SID
- 계정명, 비밀번호

Django `django.db.backends.oracle` + `oracledb`(thin mode) 조합이라 클라이언트 라이브러리
(Instant Client) 설치는 필요 없다. 접속만 되면 된다.

## 4. Helm 배포용 values 파일 작성

민감정보를 이 리포지토리의 `helm/cmdb-core/values.yaml`에 직접 쓰지 않는다. 별도 파일을
만들어서 `-f`로 얹는다 (이 파일은 git에 커밋하지 않는다):

```yaml
# values-prod.yaml
image:
  repository: harbor.internal/cmdb/cmdb-core
  tag: "1.0.0"

django:
  secretKey: "<openssl rand -base64 48 등으로 생성한 실제 값>"

database:
  engine: django.db.backends.oracle
  host: <oracle host>
  port: "1521"
  name: <oracle service name>
  user: <oracle user>
  password: "<실제 비밀번호>"

awx:
  apiKey: "<AWX 플레이북과 동일한 값으로 생성>"

service:
  nodePort: 30080   # 고정하고 싶으면 지정, 비워두면 K8s가 임의 할당
```

사내 시크릿 관리 도구를 쓴다면 위 민감값들 대신 `existingSecret: <시크릿 이름>`을 지정하면
된다 (`helm/cmdb-core/README.md` 참고).

## 5. 배포

```powershell
# 렌더링만 먼저 확인 (실제 적용 안 됨)
helm install cmdb helm/cmdb-core -f values-prod.yaml --dry-run --debug

# 실제 설치
helm install cmdb helm/cmdb-core -f values-prod.yaml
```

설치 과정에서 `manage.py migrate`를 실행하는 Job이 자동으로 한 번 돈다(Helm hook). 실패하면
`kubectl logs job/cmdb-cmdb-core-migrate`로 원인 확인.

## 6. 배포 확인

```powershell
kubectl get pods -l app.kubernetes.io/instance=cmdb
kubectl get svc cmdb-cmdb-core -o jsonpath='{.spec.ports[0].nodePort}'
```

확인된 NodePort로:

- 대시보드: `http://<노드IP>:<NodePort>/dashboard/login/` — 로그인 화면이 뜨면 정상
- admin: `http://<노드IP>:<NodePort>/admin/login/`
- facts push API: `http://<노드IP>:<NodePort>/api/facts/` (AWX가 호출할 주소)

관리자 계정이 아직 없으면:

```powershell
kubectl exec -it deploy/cmdb-cmdb-core -- python manage.py createsuperuser
```

## 7. AWX 연동

`awx/README.md` 대로 AWX Job Template을 구성하고, `cmdb_base_url`을 6번에서 확인한
NodePort 주소로 설정. `cmdb_api_key`는 5번 values 파일의 `awx.apiKey`와 반드시 동일해야
한다.

## 업그레이드 / 롤백

```powershell
helm upgrade cmdb helm/cmdb-core -f values-prod.yaml --set image.tag=1.1.0
helm rollback cmdb          # 직전 리비전으로 되돌리기
helm history cmdb           # 리비전 이력 확인
```

업그레이드도 설치와 동일하게 마이그레이션 Job이 새 파드가 뜨기 전에 먼저 실행된다.

## 체크리스트

- [ ] 이미지 빌드 (외부망) → Harbor push (폐쇄망)
- [ ] Oracle 계정/스키마 준비 완료
- [ ] `values-prod.yaml`에 실제 secretKey/DB 비밀번호/AWX API 키 채움 (git 커밋 금지)
- [ ] `helm install --dry-run --debug`로 렌더링 확인
- [ ] `helm install` 후 migrate Job 성공 확인
- [ ] 대시보드/admin/facts API 응답 확인
- [ ] 관리자 계정 생성
- [ ] AWX Job Template의 `cmdb_base_url`/`cmdb_api_key` 설정 및 테스트 push
