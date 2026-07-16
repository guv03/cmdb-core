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
