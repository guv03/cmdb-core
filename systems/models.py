from django.db import models

from core.models import Asset, TimeStampedModel


class SystemSource(TimeStampedModel):
    """vCenter 인스턴스 하나 또는 Nutanix Prism Central 하나를 가리킨다. WebConfigSource와
    달리 asset과 연결되지 않는다 - 이 소스 하나가 여러 물리 자산에 걸친 호스트/VM을 한 번에
    보고하기 때문(예: vCenter 하나가 담당하는 클러스터 전체). push마다 이 소스에 딸린
    SystemHost(+그 아래 SystemVm)를 전부 지우고 다시 만든다(diff 없이 통짜 교체 -
    webconfig/was와 같은 이유, 그 시점의 전체 스냅샷이라 사라진 호스트/VM은 다음 push에
    없으면 자동으로 정리됨)."""

    class Kind(models.TextChoices):
        VCENTER = "vcenter", "vCenter"
        NUTANIX = "nutanix", "Nutanix"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    # vCenter/Prism Central 인스턴스 식별자(예: vcenter01.corp.local) - 같은 kind 안에서도
    # 인스턴스가 여러 개일 수 있어 (kind, name)으로 소스를 구분한다.
    name = models.CharField(max_length=255)
    # 구조화 안 한 원본 응답 전체(감사/재현용) - Oracle NCLOB 대응으로 목록 화면에선 defer.
    raw_response = models.JSONField(default=dict, blank=True)
    last_pushed_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "name"], name="unique_system_source_per_kind")
        ]

    def __str__(self):
        return f"{self.get_kind_display()} / {self.name}"


class SystemHost(TimeStampedModel):
    """진짜 물리 장비(ESXi 호스트/AHV 노드) 하나 = 행 하나. "시스템" 탭의 기본 단위 -
    이 위에 떠있는 OS(VM, SystemVm)는 상세 화면에서 관계형으로 나열한다. external_id는
    vCenter/Nutanix가 내부적으로 쓰는 호스트 식별자(moref/uuid)로, SystemVm이 자신이 속한
    호스트를 찾을 때 이 값으로 매칭한다(push 페이로드 안에서만 유효한 값이라 소스 범위 안에서만
    유일하면 됨).

    클러스터/CPU/메모리/모델/전원 상태 같은 스펙은 고정 컬럼으로 안 두고 전부
    SystemHostFieldDefinition(동적 필드)로 뽑는다 - vCenter/Nutanix 응답 스키마가 버전마다
    달라 실측 검증 전이라 값이 거의 항상 비어있는 고정 컬럼을 만드는 것보다, admin에서
    실제 확인된 dot-path를 등록하는 쪽이 낫다고 판단(facts의 AUTO 필드와 같은 철학).
    `kind`는 SystemSource를 통해서만 노출한다(host 자신의 컬럼이 아님) - kind_key_overrides의
    분기 기준 자체라 동적 필드 대상이 될 수 없어 고정 유지. `vm_count`도 extra 안의 값이
    아니라 이 호스트에 연결된 SystemVm 수를 그때그때 세는 라이브 값(annotate)이라 동적 필드로
    옮길 수 없고 대시보드 쿼리에서 항상 고정으로 계산한다."""

    source = models.ForeignKey(SystemSource, on_delete=models.CASCADE, related_name="hosts")
    external_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255, blank=True)
    # kind별로만 의미있는 나머지 정보(클러스터/CPU/메모리/모델/전원 상태 등 원본 전체) -
    # 구조화 안 하고 참고용으로 보관, SystemHostFieldDefinition이 이 안에서 값을 뽑는다.
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_system_host_external_id_per_source"
            )
        ]

    def __str__(self):
        return self.name or self.external_id


class SystemVm(TimeStampedModel):
    """vCenter/Nutanix가 보고하는 VM(=OS 인스턴스) 하나 = 행 하나. host는 이 VM이 실제로
    떠있는 SystemHost(물리 장비) - 호스트 매칭에 실패하면 host=null로 저장한다(호스트 쪽
    데이터가 아직 없거나 push 시점이 어긋난 경우가 있어 이 push 자체를 막지 않는 관대한
    원칙, JEUS 컨테이너/WebToB 커넥터와 동일). asset은 hostname 매칭으로 해석하고(facts
    push로 이미 등록된 자산이어야 함), 마찬가지로 못 찾으면 asset=null.

    source는 host와 별개로 항상 채워지는 FK다 - host 매칭에 실패해도(host=null) 이 VM이
    어느 push(SystemSource)에서 왔는지는 확정적으로 알아야, 다음 push 때 "이 소스의 VM을
    전부 지우고 다시 만든다"는 통짜 교체가 host 매칭 성공 여부와 무관하게 정확히 동작한다
    (host FK 하나로만 CASCADE를 타면 host=null인 VM은 절대 안 지워지고 계속 쌓이는 버그가 됨)."""

    source = models.ForeignKey(SystemSource, on_delete=models.CASCADE, related_name="vms")
    host = models.ForeignKey(
        SystemHost, null=True, blank=True, on_delete=models.SET_NULL, related_name="vms"
    )
    asset = models.ForeignKey(
        Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="system_vms"
    )

    name = models.CharField(max_length=255, blank=True)
    # 하이퍼바이저가 보고한(또는 매칭에 쓴) hostname 원본 - asset 매칭 실패 시에도 참고용으로
    # 남겨서 왜 안 붙었는지(오타/이름 불일치 등) 화면에서 바로 알 수 있게.
    hostname = models.CharField(max_length=255, blank=True)
    uuid = models.CharField(max_length=100, blank=True)
    power_state = models.CharField(max_length=50, blank=True)
    num_cpu = models.PositiveIntegerField(null=True, blank=True)
    memory_mb = models.PositiveIntegerField(null=True, blank=True)
    primary_ip = models.GenericIPAddressField(null=True, blank=True)
    tools_status = models.CharField(max_length=50, blank=True)
    # kind별로만 의미있는 나머지 정보 - 구조화 안 하고 참고용으로만 보관.
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["host", "uuid"], name="unique_system_vm_uuid_per_host")
        ]

    def __str__(self):
        return self.name or self.hostname or self.uuid


class SystemHostFieldDefinition(TimeStampedModel):
    """SystemHost 목록 컬럼 하나 = 정의 하나 - facts 앱의 FactFieldDefinition(AUTO/MANUAL)과
    같은 목적(코드 수정 없이 admin 등록만으로 컬럼 추가)이지만, FactFieldDefinition은
    HostFact 전용으로 짜여 있어 그대로 재사용하면 facts↔systems 앱이 다시 결합돼서 이 앱
    안에 별도로 둔다(facts/webconfig/was/systems를 성격이 다른 데이터로 보고 앱 단위로
    분리해온 원칙 유지). 값 추출(coerce_fact_value/extract_json_path)은 facts.dynamic_fields의
    순수 함수를 그대로 재사용. FIXED는 없음 - facts와 달리 SystemHost엔 승인 절차 자체가
    없어서(webconfig/was와 같은 통짜 교체) 그 용도가 필요 없다."""

    class Source(models.TextChoices):
        AUTO = "auto", "자동 (extra에서 추출)"
        MANUAL = "manual", "수기 입력"

    class ValueType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOL = "bool", "Boolean"
        CHOICE = "choice", "선택형"

    key = models.CharField(
        max_length=255,
        unique=True,
        help_text=(
            "AUTO: SystemHost.extra 안의 dot-path(kind_key_overrides에 없는 kind는 이 경로를 씀), "
            "예: host_summary.hardware.cpu.count / "
            "MANUAL: extra와 무관한 고유 식별자"
        ),
    )
    # os_family_key_overrides(facts 앱)와 같은 패턴 - vCenter/Nutanix가 extra 안에 서로 다른
    # 모양으로 원본을 싣기 때문(vCenter는 extra.host_summary, Nutanix는 extra.host) kind별로
    # 다른 경로가 필요한 필드만 채우면 되고, 값이 같은 kind는 안 넣어도 key(기본 경로)를 그대로 씀.
    # MANUAL 필드는 extra 추출 자체를 안 하므로 이 값은 쓰이지 않는다.
    kind_key_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'AUTO 전용(선택). kind(vcenter/nutanix)별로 key와 다른 경로를 써야 할 때만 채움. '
            '예: {"nutanix": "host.num_cpu_cores"} (vCenter는 key를 그대로 씀)'
        ),
    )
    label = models.CharField(max_length=255)
    value_type = models.CharField(max_length=10, choices=ValueType.choices, default=ValueType.TEXT)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.AUTO)
    is_visible = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class SystemHostFieldChoice(models.Model):
    """value_type이 CHOICE인 SystemHostFieldDefinition의 선택 가능한 값 - facts의
    FactFieldChoice와 동일 패턴."""

    field_definition = models.ForeignKey(
        SystemHostFieldDefinition, on_delete=models.CASCADE, related_name="choices"
    )
    value = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["field_definition", "value"], name="unique_system_host_field_choice"
            )
        ]

    def __str__(self):
        return f"{self.field_definition.label}: {self.value}"


class SystemHostFieldValue(models.Model):
    host = models.ForeignKey(SystemHost, on_delete=models.CASCADE, related_name="field_values")
    field_definition = models.ForeignKey(SystemHostFieldDefinition, on_delete=models.CASCADE)

    value_text = models.CharField(max_length=500, null=True, blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["host", "field_definition"], name="unique_system_host_field_value"
            )
        ]

    def __str__(self):
        return f"{self.host} / {self.field_definition.key}"


class SystemDisk(TimeStampedModel):
    vm = models.ForeignKey(SystemVm, on_delete=models.CASCADE, related_name="disks")
    label = models.CharField(max_length=100, blank=True)
    size_mb = models.PositiveIntegerField(null=True, blank=True)
    storage_name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.label


class SystemNic(TimeStampedModel):
    vm = models.ForeignKey(SystemVm, on_delete=models.CASCADE, related_name="nics")
    mac_address = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    network_name = models.CharField(max_length=255, blank=True)
    is_connected = models.BooleanField(default=True)

    def __str__(self):
        return self.mac_address
