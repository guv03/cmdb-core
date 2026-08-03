from django.db import models

from core.models import Asset, Service, TimeStampedModel


class WasConfigSource(TimeStampedModel):
    """WAS 설정 원본. 종류(kind)별로 자산당 1개, push마다 구조화 테이블을 전부 지우고
    다시 만든다 - webconfig.WebConfigSource와 같은 패턴. 여기서 asset은 이 설정을 push한
    admin 서버 호스트를 가리킨다(도메인 전체를 관리하는 노드) - 도메인이 여러 물리 노드로
    클러스터링될 수 있어 이 소스에 딸린 컨테이너(JeusContainer)들의 asset과는 다를 수 있다.
    """

    class Kind(models.TextChoices):
        # domain.xml 레이아웃이 같은 JEUS 7/8/8.5/9를 kind 하나로 묶는다 - JEUS 6는
        # JEUSMain.xml + servlet_engine*/WEBMain.xml로 구조 자체가 달라 별도 kind(jeus6,
        # 아직 파서 미구현)로 분리하기로 함(CLAUDE.md "WAS 설정" 참고).
        JEUS = "jeus", "JEUS 7+"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="was_configs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    raw_content = models.TextField()
    last_pushed_at = models.DateTimeField(auto_now=True)
    # AUTO지만 WebToB/Apache/Nginx와 달리 명령어 실행이나 마커 없이 XML 루트의 version
    # 속성에서 바로 뽑힌다(parsers.parse_jeus).
    solution_version = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "kind"], name="unique_was_config_per_kind")
        ]

    def __str__(self):
        return f"{self.asset.hostname} / {self.get_kind_display()}"


class WasConfigSourceRevision(TimeStampedModel):
    """webconfig.WebConfigSourceRevision과 동일한 패턴 - raw_content가 실제로 바뀔 때만
    남기는 읽기 전용 감사 이력, 승인 절차 없음."""

    source = models.ForeignKey(WasConfigSource, on_delete=models.CASCADE, related_name="revisions")
    old_content = models.TextField()
    new_content = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source} @ {self.detected_at}"


class JeusContainer(TimeStampedModel):
    """<server> 엘리먼트 하나 = 행 하나(WebToB의 VHost/Apache의 VirtualHost에 대응).
    asset은 source.asset과 다를 수 있다 - domain.xml 하나가 여러 물리 노드의 컨테이너를
    담을 수 있어 컨테이너 자신의 node-name으로 별도 조회한다. 아직 자산으로 등록 안 된
    노드는 asset=null로 그대로 저장(하나의 push에 여러 노드가 섞여 있어 하나가 미등록이라고
    전체를 막으면 다른 정상 컨테이너까지 못 들어오므로)."""

    source = models.ForeignKey(WasConfigSource, on_delete=models.CASCADE, related_name="containers")
    asset = models.ForeignKey(
        Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="jeus_containers"
    )
    node_name = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=100)
    listen_port = models.CharField(max_length=20, blank=True)
    ssl_port = models.CharField(max_length=20, blank=True)
    deployed_apps_summary = models.TextField(blank=True)
    # 혼합 필드: webtob-connector로 연결된 WebToB vhost의 service가 정확히 하나로
    # 겹치면 push 시점에 자동으로 덮어쓴다(was/sync.py의 _resolve_webtob_service -
    # 이중화로 connector가 여러 개 붙어도 실제 서비스는 같은 게 보통이라 자동 채움 가능).
    # 값이 없거나 여러 개로 갈리면(연결이 아예 없는 컨테이너 포함) 기존 값을 그대로 두고
    # 대시보드에서 수기 입력한 값이 보존된다. webconfig.WebtobVhost.service와 같은
    # core.Service를 참조해야 오타 없이 WebToB<->JEUS 서비스 전파가 성립한다.
    service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="jeus_containers"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "name"], name="unique_jeus_container_name_per_source")
        ]

    def __str__(self):
        return self.name


class JeusWebtobConnector(TimeStampedModel):
    """<webtob-connector> 하나 = 행 하나. 이 JEUS 컨테이너가 등록되는 WebToB 쪽 정보
    (registration-id/network-address)를 담고, 동기화 시점에 webconfig 앱의
    WebtobServer로 실제 연결을 해석해둔다(registration-id == WebtobServer.name,
    network-address로 그 WebToB가 설치된 자산을 찾아 같은 자산+같은 이름인 서버로 매칭).
    못 찾으면 webtob_server=null로 두고 다음 JEUS push 때 재해석(컨테이너 asset=null과
    같은 관대한 원칙 - WebToB 쪽 데이터가 아직 안 들어왔을 수 있어서 이 push 자체를 막지 않음).
    """

    container = models.ForeignKey(JeusContainer, on_delete=models.CASCADE, related_name="webtob_connectors")
    name = models.CharField(max_length=100)
    registration_id = models.CharField(max_length=100, blank=True)
    network_address = models.CharField(max_length=255, blank=True)
    port = models.CharField(max_length=20, blank=True)
    wjp_version = models.CharField(max_length=20, blank=True)
    webtob_server = models.ForeignKey(
        "webconfig.WebtobServer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jeus_connectors",
    )

    def __str__(self):
        return self.name
