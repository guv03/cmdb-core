from django.db import models

from core.models import Asset, Service, TimeStampedModel


class WebConfigSource(TimeStampedModel):
    """웹서버 설정 원본. 종류(kind)별로 자산당 1개, push마다 통째로 교체된다."""

    class Kind(models.TextChoices):
        WEBTOB = "webtob", "WEBTOB"
        APACHE = "apache", "Apache"
        NGINX = "nginx", "Nginx"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="web_configs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    raw_content = models.TextField()
    # 구조화 테이블로 안 뽑은 나머지 절(EXT/ALIAS/LOGGING/ERRORDOCUMENT 등) - 원본 펼쳐보기용, 조회 대상 아님
    extra_sections = models.JSONField(default=dict, blank=True)
    last_pushed_at = models.DateTimeField(auto_now=True)
    # AUTO: push된 원본에서 "# CMDB_SOLUTION_VERSION: ..." 마커를 찾아 자동 추출(webtob는
    # wsadmin -version 출력, webconfig/version_extract.py 참고). 마커가 없는 push는 기존 값을
    # 그대로 둔다(무조건 덮어쓰지 않음 - 아직 마커를 안 보내는 자산/kind의 값이 사라지지 않게).
    solution_version = models.CharField(max_length=50, blank=True)
    # Fix/패치 정보. WebtoB만 해당(예: "SP 0 Fix #4 Linux-K2.6_x64 FD16384 B404 epoll 2026/05/19")
    # - nginx/apache 등은 이 값이 없는 게 정상이라 비워둔다.
    solution_fix = models.CharField(max_length=255, blank=True)
    # AUTO: AWX가 이 설정을 읽어온 원본 파일 전체 경로(예: /app/webtob/config/http.m).
    # solution_version과 동일한 롤아웃 안전 원칙 - payload에 없으면(아직 role 업데이트 전
    # 자산) 기존 값을 그대로 두고 덮어쓰지 않는다(webconfig/views.py).
    config_path = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "kind"], name="unique_web_config_per_kind")
        ]

    def __str__(self):
        return f"{self.asset.hostname} / {self.get_kind_display()}"


class WebConfigSourceRevision(TimeStampedModel):
    """웹설정 원본(raw_content)이 실제로 바뀔 때만 남기는 읽기 전용 감사 이력 - facts의
    PendingChange와 달리 승인 절차는 없다(웹설정 push는 지금처럼 즉시 반영 유지). old/new를
    한 행에 같이 저장해서 조회 시점에 이전 리비전을 따로 찾아 짝지을 필요가 없게 한다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="revisions")
    old_content = models.TextField()
    new_content = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source} @ {self.detected_at}"


class WebtobNode(TimeStampedModel):
    """*NODE 절 - 소스당 1개(WebtoB 프로세스 자체 설정)."""

    source = models.OneToOneField(WebConfigSource, on_delete=models.CASCADE, related_name="node")
    name = models.CharField(max_length=100)
    webtobdir = models.CharField(max_length=255, blank=True)
    docroot = models.CharField(max_length=255, blank=True)
    port = models.CharField(max_length=20, blank=True)
    hth = models.CharField(max_length=20, blank=True)
    limit_request_body = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class WebtobSsl(TimeStampedModel):
    """*SSL 절 - VHost가 이름으로 참조한다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="ssl_entries")
    name = models.CharField(max_length=100)
    certificate_file = models.CharField(max_length=500, blank=True)
    certificate_key_file = models.CharField(max_length=500, blank=True)
    protocols = models.CharField(max_length=255, blank=True)
    required_ciphers = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_ssl_name_per_source")
        ]

    def __str__(self):
        return self.name


class WebtobVhost(TimeStampedModel):
    """*VHOST 절 - 다른 절들이 참조하는 중심 엔티티."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="vhosts")
    name = models.CharField(max_length=100)
    hostname = models.CharField(max_length=255, blank=True)
    hostalias = models.CharField(max_length=500, blank=True)
    docroot = models.CharField(max_length=255, blank=True)
    port = models.CharField(max_length=20, blank=True)
    ssl_flag = models.BooleanField(default=False)
    ssl = models.ForeignKey(
        WebtobSsl, null=True, blank=True, on_delete=models.SET_NULL, related_name="vhosts"
    )
    # *VHOST절 원본은 *LOGGING절 엔트리 이름(예: "log1")만 담고 있는데, sync_webtob이
    # 그 이름으로 *LOGGING절을 찾아 FileName으로 resolve해서 저장한다(대시보드에 이름이
    # 아니라 실제 로그 경로가 보이도록) - 매칭 실패 시 원래 이름값으로 폴백.
    logging = models.CharField(max_length=255, blank=True)
    errorlog = models.CharField(max_length=255, blank=True)
    # 수기 입력: 이 vhost가 어떤 서비스인지. AUTO 필드와 달리 push로 덮어쓰지 않음(sync_webtob이
    # vhost를 이름으로 upsert하고 이 필드는 defaults에서 빠져있어 보존됨). Service FK라
    # 오타 없이 WAS(JeusContainer.service)와 정확히 같은 값을 참조할 수 있다.
    service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="webtob_vhosts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_vhost_name_per_source")
        ]

    def __str__(self):
        return self.name


class WebtobSvrGroup(TimeStampedModel):
    """*SVRGROUP 절 - VhostName이 없는 것도 있고(공용 그룹, 예: 정적 HTML용 htmlg),
    콤마로 여러 vhost를 한 번에 지정하는 경우도 있어(예: "vhost1,vhost1_ssl") M2M로 둔다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="svrgroups")
    name = models.CharField(max_length=100)
    svrtype = models.CharField(max_length=50, blank=True)
    vhosts = models.ManyToManyField(WebtobVhost, blank=True, related_name="svrgroups")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_svrgroup_name_per_source")
        ]

    def __str__(self):
        return self.name


class WebtobServer(TimeStampedModel):
    """*SERVER 절 - SVGNAME으로 SvrGroup을 참조한다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="servers")
    name = models.CharField(max_length=100)
    svrgroup = models.ForeignKey(
        WebtobSvrGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="servers"
    )
    minproc = models.PositiveIntegerField(null=True, blank=True)
    maxproc = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_server_name_per_source")
        ]

    def __str__(self):
        return self.name


class WebServiceDomain(TimeStampedModel):
    """도메인 기준으로 서비스를 조회하기 위한 요약 테이블. vhost 하나당 한 행(kind별 sync 함수가
    push마다 통째로 재생성). 주 도메인(hostname)만 domain에 담고 나머지 별칭은 aliases에
    콤마로 모아둬 화면이 vhost 개수만큼만 늘어나게 한다 - 검색은 둘 다 대상으로 한다.
    service_name은 해당 vhost.service.name을 그대로 복사해두는 것이라(Service FK가 아니라
    이름 문자열만 저장 - 도메인 기준 조회/검색에는 이 정도로 충분) vhost 쪽 서비스가 바뀌면
    함께 갱신해야 한다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="service_domains")
    vhost_name = models.CharField(max_length=100)
    domain = models.CharField(max_length=255)
    aliases = models.CharField(max_length=500, blank=True)
    port = models.CharField(max_length=20, blank=True)
    service_name = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "vhost_name"], name="unique_service_domain")
        ]

    def __str__(self):
        return self.domain


class WebtobUri(TimeStampedModel):
    """*URI 절 - VhostName으로 VHost를(콤마로 여러 개 지정 가능해 M2M), SvrName으로 Server를 참조한다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="uris")
    name = models.CharField(max_length=100)
    uri_path = models.CharField(max_length=500, blank=True)
    vhosts = models.ManyToManyField(WebtobVhost, blank=True, related_name="uris")
    server = models.ForeignKey(
        WebtobServer, null=True, blank=True, on_delete=models.SET_NULL, related_name="uris"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_uri_name_per_source")
        ]

    def __str__(self):
        return self.name


class ApacheVhost(TimeStampedModel):
    """<VirtualHost> 블록 하나 = 행 하나. WebToB의 SvrGroup/Server/Uri 같은 관계형 모델링은
    안 하고(리버스 프록시 용도뿐이라 그 정도 깊이가 불필요) ProxyPass 대상은 proxy_summary에
    요약 문자열로만 담는다. hostname/hostalias/port/service 필드명을 WebtobVhost와
    맞춰서 sync_service_domains()를 수정 없이 그대로 재사용한다. name은 설정 파일에 vhost
    자신을 가리키는 별도 식별자가 없어 "hostname:port"로 합성 - push마다 안정적이어야
    upsert 시 수기 입력한 service가 보존된다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="apache_vhosts")
    name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255, blank=True)
    hostalias = models.CharField(max_length=500, blank=True)
    port = models.CharField(max_length=20, blank=True)
    docroot = models.CharField(max_length=255, blank=True)
    ssl_flag = models.BooleanField(default=False)
    ssl_certificate_file = models.CharField(max_length=500, blank=True)
    ssl_certificate_key_file = models.CharField(max_length=500, blank=True)
    # SSLProtocol/SSLCipherSuite - vhost 안에 직접 없으면 <VirtualHost> 밖의 전역 mod_ssl
    # 설정으로 폴백해서 채운다(webconfig/parsers.py의 parse_apache 참고, WebtobSsl과 같은
    # 이유로 ciphers만 TextField - 길이 제한 없이 그대로 담기 위함).
    ssl_protocols = models.CharField(max_length=255, blank=True)
    ssl_ciphers = models.TextField(blank=True)
    logging = models.CharField(max_length=255, blank=True)
    errorlog = models.CharField(max_length=255, blank=True)
    proxy_summary = models.TextField(blank=True)
    # 수기 입력: WebtobVhost.service와 동일 취급 - push 동기화 대상에서 빠져 보존됨.
    service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="apache_vhosts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_apache_vhost_name_per_source")
        ]

    def __str__(self):
        return self.name


class NginxVhost(TimeStampedModel):
    """server {} 블록 하나 = 행 하나. ApacheVhost와 같은 이유로 관계형 모델링 없이
    proxy_summary 요약 문자열만 둔다."""

    source = models.ForeignKey(WebConfigSource, on_delete=models.CASCADE, related_name="nginx_vhosts")
    name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255, blank=True)
    hostalias = models.CharField(max_length=500, blank=True)
    port = models.CharField(max_length=20, blank=True)
    listen = models.CharField(max_length=255, blank=True)
    docroot = models.CharField(max_length=255, blank=True)
    ssl_flag = models.BooleanField(default=False)
    ssl_certificate_file = models.CharField(max_length=500, blank=True)
    ssl_certificate_key_file = models.CharField(max_length=500, blank=True)
    # ssl_protocols/ssl_ciphers - server{} 안에 직접 없으면 http{} 최상위 설정으로 폴백해서
    # 채운다(webconfig/parsers.py의 parse_nginx 참고, ApacheVhost와 동일 취지).
    ssl_protocols = models.CharField(max_length=255, blank=True)
    ssl_ciphers = models.TextField(blank=True)
    logging = models.CharField(max_length=255, blank=True)
    errorlog = models.CharField(max_length=255, blank=True)
    proxy_summary = models.TextField(blank=True)
    service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="nginx_vhosts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_nginx_vhost_name_per_source")
        ]

    def __str__(self):
        return self.name
