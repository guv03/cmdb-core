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
        CHOICE = "choice", "선택형"

    class Source(models.TextChoices):
        AUTO = "auto", "자동 (raw facts 승격)"
        MANUAL = "manual", "수기 입력"
        FIXED = "fixed", "고정 컬럼"

    key = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            "AUTO: raw_facts 안의 dot-path(os_family_key_overrides에 없는 os_family는 이 경로를 씀), "
            "예: ansible_facts.ansible_memtotal_mb / "
            "MANUAL: raw_facts와 무관한 고유 식별자 / "
            "FIXED: HostFact 고정 컬럼명(facts.approval.FIXED_FIELD_EXTRACTORS 참고)"
        ),
    )
    os_family_key_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "AUTO 필드 전용(선택). os_family(예: Windows/RedHat/AIX)별로 key와 다른 경로를 써야 할 "
            "때만 그 os_family만 채움 — 값이 같은 os_family는 안 넣어도 되고, 그 경우 key(기본 경로)를 "
            '그대로 씀. 예1(다른 OS가 하나): {"Windows": "ansible_facts.distribution"} '
            "(distribution_version이 리눅스는 사람이 읽는 버전이지만 윈도우는 커널 빌드번호라서, "
            "key=ansible_facts.distribution_version을 기본으로 두고 Windows만 이렇게 재정의). "
            '예2(다른 OS가 둘 이상): {"Windows": "ansible_facts.distribution", '
            '"AIX": "ansible_facts.oslevel"} (윈도우/AIX 둘 다 기본 경로와 다르면 같은 JSON 안에 '
            "os_family 키를 나란히 추가 — 셋 이상도 같은 방식)"
        ),
    )
    label = models.CharField(max_length=255)
    value_type = models.CharField(max_length=10, choices=ValueType.choices)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.AUTO)
    is_visible = models.BooleanField(
        default=True, help_text="FIXED 필드는 이미 고정 컬럼으로 표시되므로 항상 꺼둘 것"
    )
    is_searchable = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    requires_approval = models.BooleanField(
        default=False,
        help_text="켜두면 이미 존재하는 자산의 값이 push로 바뀔 때 즉시 반영하지 않고 승인 대기열에 쌓는다. MANUAL 필드는 대상이 아님(대시보드 입력은 항상 즉시 반영)",
    )

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class FactFieldChoice(models.Model):
    """value_type이 CHOICE인 필드에서 선택 가능한 값 목록. admin에서 필드 정의와 함께 관리한다."""

    field_definition = models.ForeignKey(
        FactFieldDefinition, on_delete=models.CASCADE, related_name="choices"
    )
    value = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["field_definition", "value"], name="unique_field_choice"
            )
        ]

    def __str__(self):
        return f"{self.field_definition.label}: {self.value}"


class PendingChange(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        APPROVED = "approved", "승인"
        REJECTED = "rejected", "반려"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="pending_changes")
    field_definition = models.ForeignKey(
        FactFieldDefinition, on_delete=models.CASCADE, related_name="pending_changes"
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
        return f"{self.asset.hostname} / {self.field_definition.key}"

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
