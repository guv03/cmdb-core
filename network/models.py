from django.db import models

from core.models import Asset, Service, TimeStampedModel


class ServiceNetworkMapping(TimeStampedModel):
    """서비스 하나의 외부/내부망 접속 경로(도메인 -> 공인IP -> 내부VIP -> 실서버들) 매핑 -
    "홉(hop)" 하나 = 행 하나. 처음엔 서비스당 딱 하나(OneToOne)만 뒀는데, WEB(Apache/Nginx)
    ->GW->WAS처럼 같은 서비스 안에서 VIP를 두 번 거치는 실제 구성(WEB은 외부 도메인/공인IP +
    그 뒤 VIP1, GW는 내부망이라 도메인/공인IP 없이 VIP2)이 있어서 서비스당 여러 개를 허용하는
    ForeignKey로 바꿨다. hop_order(0부터)로 체인 순서를 매기고, 그래프(topology.py)는 hop 0의
    "from"을 WEB vhost로, hop N(N>0)의 "from"을 hop N-1의 실서버로, 마지막 hop의 실서버만
    기존처럼 WAS 컨테이너 노드와 asset 매칭을 시도한다 - 중간 hop(예: GW)의 실서버는 CMDB가
    아예 추적하지 않는 장비일 수 있어 그래프에 개별 노드로는 안 그리고(리소스 목록 표에서는
    hop마다 전부 나열) VIP 노드 체인만 이어서 보여준다. label은 "WEB", "GW"처럼 hop을
    구분하는 자유 텍스트(빈 값이면 "VIP"로 표시) - 조직마다 계층 이름이 달라 고정 선택지로
    안 두고 완전 자유 입력.

    WebToB<->JEUS는 설정 내용(webtob-connector)에서 실제 연결을 결정적으로 뽑아낼 수 있지만,
    Apache/Nginx는 뒷단을 VIP/도메인 하나로만 지정해서(운영계 이중화 구성) 설정 파일 자체에
    어떤 실서버가 몇 대 있는지 정보가 전혀 없다 - 어떤 push에도 안 나오는 순수 사람 지식이라
    admin/대시보드에서 직접 등록하는 수밖에 없다.

    앵커를 Service로 잡은 이유: ApacheVhost/JeusContainer처럼 push마다 통짜 재생성되는 모델에
    이 매핑을 FK로 매달면 SystemHost가 처음 겪었던 "다음 push 때 MANUAL 값 증발" 버그를 그대로
    재현한다. Service는 push로 안 건드려지는 안정적인 앵커라 이 문제가 없다.

    내부망 전용 hop은 external_domain/external_ip를 비워두면 된다 - 별도 구분 필드(zone 등)를
    두지 않고 값 유무로 구분한다."""

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="network_mappings")
    # 체인 순서 - 삭제로 값 사이에 구멍이 생겨도 상관없다(정렬 기준일 뿐, 정렬된 결과의
    # "몇 번째냐"로 체인을 잇지 raw 값 자체의 연속성엔 의미를 안 둠).
    hop_order = models.PositiveIntegerField(default=0)
    label = models.CharField(max_length=100, blank=True, help_text="이 구간을 구분하는 이름 (예: WEB, GW)")
    external_domain = models.CharField(max_length=255, blank=True, help_text="외부망 구간만 해당 (예: www.example.com)")
    external_ip = models.CharField(max_length=255, blank=True, help_text="외부 공인 IP (외부망 구간만 해당)")
    internal_vip = models.CharField(max_length=255, blank=True, help_text="내부 VIP (L4/로드밸런서 가상 IP)")

    class Meta:
        ordering = ["hop_order"]
        constraints = [
            models.UniqueConstraint(fields=["service", "hop_order"], name="unique_hop_order_per_service")
        ]

    def __str__(self):
        return f"{self.service.name} · {self.label or 'VIP'}"


class ServiceNetworkBackend(TimeStampedModel):
    """internal_vip 뒤에 실제로 붙는 서버 목록(이중화 시 2대 이상). asset은 hostname/IP로
    매칭을 시도하되(was.sync._resolve_webtob_asset과 같은 관대한 원칙) 못 찾으면 asset=null로
    원본 문자열만 보존 - 아직 CMDB에 등록 안 된 서버일 수 있으므로."""

    mapping = models.ForeignKey(ServiceNetworkMapping, on_delete=models.CASCADE, related_name="backends")
    ip_or_hostname = models.CharField(max_length=255)
    asset = models.ForeignKey(
        Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name="network_backend_entries"
    )

    class Meta:
        ordering = ["ip_or_hostname"]

    def __str__(self):
        return self.ip_or_hostname
