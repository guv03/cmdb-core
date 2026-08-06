from django.db import models

from core.models import Asset, Service, TimeStampedModel


class WasConfigSource(TimeStampedModel):
    """WAS 설정 원본. 종류(kind)+instance_name별로 자산당 1개, push마다 구조화 테이블을
    전부 지우고 다시 만든다 - webconfig.WebConfigSource와 같은 패턴. 여기서 asset은 이
    설정을 push한 admin 서버 호스트를 가리킨다(도메인 전체를 관리하는 노드) - 도메인이
    여러 물리 노드로 클러스터링될 수 있어 이 소스에 딸린 컨테이너(JeusContainer)들의
    asset과는 다를 수 있다.
    """

    class Kind(models.TextChoices):
        # domain.xml 레이아웃이 같은 JEUS 7/8/8.5/9를 kind 하나로 묶는다 - JEUS 6는
        # JEUSMain.xml + servlet_engine*/WEBMain.xml로 구조 자체가 달라 별도 kind로 분리
        # (CLAUDE.md "WAS 설정" 참고).
        JEUS = "jeus", "JEUS"
        JEUS6 = "jeus6", "JEUS6"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="was_configs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # JEUS6은 같은 물리 호스트에 OS 계정만 다르게 해서 여러 인스턴스가 뜰 수 있어(예: ddorap01에
    # jeuscm/jeuslt 계정으로 각각 별도 JEUS6) asset+kind만으로는 유일하지 않다. JEUSMain.xml
    # 내용만으로는 인스턴스를 구분할 방법이 없어(apache/nginx의 hostname과 같은 이유) AWX가
    # payload에 명시적으로 실어 보낸다(OS 계정명 그대로, 예: "jeuscm") - was/parsers.py는
    # 이 값을 몰라도 되고 was/views.py가 asset/kind와 별개로 그대로 저장만 한다. kind=jeus는
    # admin 서버 한 대 = 도메인 하나라 이 문제가 없어 항상 빈 문자열로 둔다.
    instance_name = models.CharField(max_length=100, blank=True)
    raw_content = models.TextField()
    last_pushed_at = models.DateTimeField(auto_now=True)
    # AUTO지만 WebToB/Apache/Nginx와 달리 명령어 실행이나 마커 없이 XML 루트의 version
    # 속성에서 바로 뽑힌다(parsers.parse_jeus).
    solution_version = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "kind", "instance_name"], name="unique_was_config_per_instance"
            )
        ]

    def __str__(self):
        label = f"{self.asset.hostname} / {self.get_kind_display()}"
        return f"{label} ({self.instance_name})" if self.instance_name else label


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


class JeusDataSource(TimeStampedModel):
    """<resources><data-source><database> 엘리먼트 하나 = 행 하나 - domain.xml 레벨에서
    정의되는 JDBC 커넥션 풀로, 특정 컨테이너에 속하지 않는다(WebToB의 SvrGroup/Uri처럼
    도메인 공용 리소스). 각 <server>(JeusContainer)의 <data-sources><data-source>이름
    </data-source>이 이 data_source_id를 이름으로 참조하는 방식이고, 하나의 데이터소스를
    여러 컨테이너가 공유하는 게 일반적이라(SvrGroup이 VhostName으로 여러 vhost를 참조하는
    것과 같은 이유) M2M으로 연결한다(was/sync.py). password는 설정 파일에 암호화된 값으로
    있지만 그래도 민감정보라 CMDB엔 아예 저장하지 않는다 - 필요하면 상세 화면의 "원본 설정
    보기"에서 원문(암호화된 값)을 확인."""

    source = models.ForeignKey(WasConfigSource, on_delete=models.CASCADE, related_name="data_sources")
    containers = models.ManyToManyField(JeusContainer, blank=True, related_name="data_sources")
    data_source_id = models.CharField(max_length=100)
    export_name = models.CharField(max_length=100, blank=True)
    vendor = models.CharField(max_length=50, blank=True)
    db_host = models.CharField(max_length=255, blank=True)
    port = models.CharField(max_length=20, blank=True)
    database_name = models.CharField(max_length=100, blank=True)
    db_user = models.CharField(max_length=100, blank=True)
    pool_min = models.PositiveIntegerField(null=True, blank=True)
    pool_max = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "data_source_id"], name="unique_jeus_datasource_per_source"
            )
        ]

    def __str__(self):
        return self.data_source_id


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
