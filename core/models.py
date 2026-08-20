from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Asset(TimeStampedModel):
    hostname = models.CharField(max_length=255, unique=True, db_index=True)
    primary_ip = models.GenericIPAddressField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_changed_at = models.DateTimeField(
        null=True, blank=True, help_text="승인 대상 필드의 변경이 승인되어 반영된 시각"
    )
    # 서비스 라벨은 기본적으로 이 asset에 연결된 WEB vhost/WAS 컨테이너의 service를
    # 역추적해서 계산한다(dashboard.queries.get_service_labels_for_assets) - 저장값이
    # 아니라 매번 계산. 하지만 그 역추적 경로(WebToB<->JEUS 커넥터, hostname 매칭 등)가
    # 끊기면(예: DB 전용 서버처럼 애초에 WEB/WAS가 없는 asset, 또는 커넥터 설정 누락) 라벨이
    # 아예 안 뜨는 "구멍"이 생길 수 있어, 그 구멍을 메꾸는 수기 보정값을 별도로 둔다 - 계산값과
    # 합집합으로 합쳐서 노출된다(대체가 아니라 보충). Asset은 push로 통짜 교체되지 않는
    # 안정적인 엔티티라(hostname 기준 update_or_create) 이 필드를 직접 붙여도 값이 사라질
    # 위험이 없다(DbInstance처럼 push마다 재생성되는 모델과는 다름 - 그런 경우 database.DbConfigSource
    # 처럼 안 지워지는 상위 엔티티에 붙여야 한다).
    manual_services = models.ManyToManyField(
        "Service", blank=True, related_name="manual_assets"
    )

    class Meta:
        ordering = ["hostname"]

    def __str__(self):
        return self.hostname


class Service(TimeStampedModel):
    """WEB(vhost)/WAS(컨테이너)를 가로질러 "같은 서비스"를 묶는 엔티티. WebToB<->JEUS처럼
    구조적으로 연결된 vhost/컨테이너는 한쪽 서비스를 바꾸면 반대쪽도 같이 맞춰지는데, 그러려면
    양쪽이 문자열이 아니라 이 모델을 같이 참조해야 오타로 어긋나지 않는다."""

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
