from django.db import models

from core.models import Asset, TimeStampedModel


class WebConfigSource(TimeStampedModel):
    """웹서버 설정 원본. 종류(kind)별로 자산당 1개, push마다 통째로 교체된다."""

    class Kind(models.TextChoices):
        WEBTOB = "webtob", "WebtoB"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="web_configs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    raw_content = models.TextField()
    # 구조화 테이블로 안 뽑은 나머지 절(EXT/ALIAS/LOGGING/ERRORDOCUMENT 등) - 원본 펼쳐보기용, 조회 대상 아님
    extra_sections = models.JSONField(default=dict, blank=True)
    last_pushed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "kind"], name="unique_web_config_per_kind")
        ]

    def __str__(self):
        return f"{self.asset.hostname} / {self.get_kind_display()}"


class WebtobNode(TimeStampedModel):
    """*NODE 절 - 소스당 1개(WebtoB 프로세스 자체 설정)."""

    source = models.OneToOneField(WebConfigSource, on_delete=models.CASCADE, related_name="node")
    name = models.CharField(max_length=100)
    webtobdir = models.CharField(max_length=255, blank=True)
    docroot = models.CharField(max_length=255, blank=True)
    port = models.CharField(max_length=20, blank=True)
    hth = models.CharField(max_length=20, blank=True)

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
    logging = models.CharField(max_length=100, blank=True)
    errorlog = models.CharField(max_length=100, blank=True)

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
