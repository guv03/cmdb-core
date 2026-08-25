from django.db import models

from core.models import Asset, TimeStampedModel


class NetworkRoute(TimeStampedModel):
    """도메인 또는 VIP 하나 = 행 하나. "이 주소로 부르면 실제로 어디로 가는지"를 사람이 직접
    등록해두는 참고용 라우팅 정보 - Apache/Nginx는 ProxyPass 대상을 VIP/도메인 하나로만
    지정하는 운영계 이중화 구성이 흔한데, 그 뒤에 실제로 실서버가 몇 대인지는 설정 파일 어디에도
    안 나온다(어떤 push로도 못 얻는 순수 사람 지식).

    처음엔 이 테이블이 core.Service에 FK로 묶여 "서비스 하나 = 홉 여러 개(hop_order 체인)"
    구조였으나, 실사용해보니 사람이 서비스를 먼저 골라 그 밑에 홉을 입력하는 흐름 자체가 실제
    의도(도메인/VIP로 호출하는 게 있으면 그 주소를 보고 자동으로 추적해서 연결)와 어긋난다는
    피드백으로 갈아엎었다. 이제는 서비스와 완전히 무관한 독립된 라우팅 테이블이고, 구성도
    (dashboard/topology.py)가 Apache/Nginx vhost의 proxy_summary(ProxyPass 대상, 비구조화
    텍스트) 안에 이 라우트의 key 값이 문자열로 포함되어 있으면 자동으로 찾아 연결한다 -
    사람이 미리 서비스와 연결지어둘 필요가 없다.

    체인(도메인 -> VIP -> VIP -> 실서버)도 hop_order 같은 명시적 순서 필드 없이, backends 중
    하나가 다시 다른 NetworkRoute.key와 정확히 일치하면 재귀적으로 다음 라우트를 찾아가는
    방식으로 자동 구성된다(network/resolve.py의 resolve_chain) - 등록 순서를 사람이 관리할
    필요가 없다."""

    key = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            "이 경로를 찾는 값 - 도메인 또는 VIP (예: www.example.com, 10.0.0.1). "
            "Apache/Nginx의 ProxyPass 대상 텍스트에 이 값이 포함되면 구성도에서 자동으로 연결됩니다."
        ),
    )
    label = models.CharField(max_length=100, blank=True, help_text="구분용 이름 (예: WEB, GW) - 참고용, 검색/매칭에는 안 쓰임")
    note = models.CharField(max_length=255, blank=True, help_text="비고")

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class NetworkRouteBackend(TimeStampedModel):
    """route.key 뒤에 실제로 붙는 서버 또는 다음 라우트 목록(이중화 시 2대 이상). 값이 다른
    NetworkRoute.key와 정확히 일치하면 체인이 이어지고(예: VIP1 -> VIP2), 아니면 실서버로 보고
    asset을 hostname/IP로 매칭 시도한다(network/resolve.py의 resolve_backend_asset, was/sync.py
    의 _resolve_webtob_asset과 같은 관대한 원칙) - 못 찾으면 asset=null로 원본 문자열만 보존."""

    route = models.ForeignKey(NetworkRoute, on_delete=models.CASCADE, related_name="backends")
    ip_or_hostname = models.CharField(max_length=255)
    asset = models.ForeignKey(
        Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name="network_backend_entries"
    )

    class Meta:
        ordering = ["ip_or_hostname"]

    def __str__(self):
        return self.ip_or_hostname
