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

    class Meta:
        ordering = ["hostname"]

    def __str__(self):
        return self.hostname
