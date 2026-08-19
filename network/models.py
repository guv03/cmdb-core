from django.db import models

from core.models import Asset, Service, TimeStampedModel


class ServiceNetworkMapping(TimeStampedModel):
    """서비스 하나의 외부/내부망 접속 경로(도메인 -> 공인IP -> 내부VIP -> 실서버들) 매핑.

    WebToB<->JEUS는 설정 내용(webtob-connector)에서 실제 연결을 결정적으로 뽑아낼 수 있지만,
    Apache/Nginx는 뒷단을 VIP/도메인 하나로만 지정해서(운영계 이중화 구성) 설정 파일 자체에
    어떤 실서버가 몇 대 있는지 정보가 전혀 없다 - 어떤 push에도 안 나오는 순수 사람 지식이라
    admin/대시보드에서 직접 등록하는 수밖에 없다.

    앵커를 Service로 잡은 이유: ApacheVhost/JeusContainer처럼 push마다 통짜 재생성되는 모델에
    이 매핑을 FK로 매달면 SystemHost가 처음 겪었던 "다음 push 때 MANUAL 값 증발" 버그를 그대로
    재현한다. Service는 push로 안 건드려지는 안정적인 앵커라 이 문제가 없다.

    내부망 전용 서비스는 external_domain/external_ip를 비워두면 된다 - 별도 구분 필드(zone
    등)를 두지 않고 값 유무로 구분한다."""

    service = models.OneToOneField(Service, on_delete=models.CASCADE, related_name="network_mapping")
    external_domain = models.CharField(max_length=255, blank=True, help_text="외부망 서비스만 해당 (예: www.example.com)")
    external_ip = models.CharField(max_length=255, blank=True, help_text="외부 공인 IP (외부망 서비스만 해당)")
    internal_vip = models.CharField(max_length=255, blank=True, help_text="내부 VIP (L4/로드밸런서 가상 IP)")

    def __str__(self):
        return f"{self.service.name} 네트워크 매핑"


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
