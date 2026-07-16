from django.db import models

from core.models import Asset, TimeStampedModel


class HostFact(TimeStampedModel):
    class SourcePlatform(models.TextChoices):
        VCENTER = "vcenter", "vCenter"
        NUTANIX = "nutanix", "Nutanix"
        PHYSICAL = "physical", "Physical"
        UNKNOWN = "unknown", "Unknown"

    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="hostfact")

    os_family = models.CharField(max_length=100, blank=True)
    os_version = models.CharField(max_length=100, blank=True)

    source_platform = models.CharField(
        max_length=20, choices=SourcePlatform.choices, null=True, blank=True
    )
    vm_uuid = models.CharField(max_length=100, null=True, blank=True)
    cluster_name = models.CharField(max_length=255, null=True, blank=True)
    power_state = models.CharField(max_length=50, null=True, blank=True)
    num_cpu = models.PositiveIntegerField(null=True, blank=True)
    memory_mb = models.PositiveIntegerField(null=True, blank=True)

    raw_facts = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.asset.hostname


class FactFieldDefinition(TimeStampedModel):
    class ValueType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOL = "bool", "Boolean"

    key = models.CharField(
        max_length=255,
        unique=True,
        help_text="raw_facts 안의 dot-path, 예: ansible_facts.ansible_memtotal_mb",
    )
    label = models.CharField(max_length=255)
    value_type = models.CharField(max_length=10, choices=ValueType.choices)
    is_visible = models.BooleanField(default=True)
    is_searchable = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class ApprovalFieldConfig(TimeStampedModel):
    """이 필드의 값 변경은 자동 반영하지 않고 admin 승인을 거치게 한다."""

    class SourceType(models.TextChoices):
        FIXED = "fixed", "고정 컬럼"
        DYNAMIC = "dynamic", "동적 필드"

    source_type = models.CharField(max_length=10, choices=SourceType.choices)
    key = models.CharField(
        max_length=255,
        help_text="fixed: HostFact 고정 컬럼명 / dynamic: FactFieldDefinition.key와 동일한 값",
    )
    label = models.CharField(max_length=255)
    value_type = models.CharField(max_length=10, choices=FactFieldDefinition.ValueType.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source_type", "key"], name="unique_approval_field")
        ]

    def __str__(self):
        return self.label


class PendingChange(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        APPROVED = "approved", "승인"
        REJECTED = "rejected", "반려"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="pending_changes")
    field_config = models.ForeignKey(
        ApprovalFieldConfig, on_delete=models.CASCADE, related_name="pending_changes"
    )

    old_value_text = models.CharField(max_length=500, null=True, blank=True)
    old_value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    old_value_date = models.DateField(null=True, blank=True)

    new_value_text = models.CharField(max_length=500, null=True, blank=True)
    new_value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    new_value_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.asset.hostname} / {self.field_config.key}"

    @property
    def old_value(self):
        return self.old_value_text if self.old_value_text is not None else self.old_value_number if self.old_value_number is not None else self.old_value_date

    @property
    def new_value(self):
        return self.new_value_text if self.new_value_text is not None else self.new_value_number if self.new_value_number is not None else self.new_value_date


class HostFactValue(models.Model):
    host_fact = models.ForeignKey(HostFact, on_delete=models.CASCADE, related_name="values")
    field_definition = models.ForeignKey(FactFieldDefinition, on_delete=models.CASCADE)

    value_text = models.CharField(max_length=500, null=True, blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["host_fact", "field_definition"], name="unique_host_fact_field"
            )
        ]
        indexes = [
            models.Index(fields=["field_definition", "value_text"]),
            models.Index(fields=["field_definition", "value_number"]),
        ]

    def __str__(self):
        return f"{self.host_fact.asset.hostname} / {self.field_definition.key}"
