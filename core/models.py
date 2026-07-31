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
