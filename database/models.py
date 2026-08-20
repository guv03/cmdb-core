from django.db import models

from core.models import Asset, Service, TimeStampedModel


class DbConfigSource(TimeStampedModel):
    """DB 하나(Standalone이든 RAC든) = 행 하나. WebToB/JEUS와 달리 매칭·업서트 키가
    (asset, kind)가 아니라 **(kind, db_unique_name)**이다 - db_unique_name은 Oracle이
    보장하는 전역 유일 식별자라(Standby DB도 Primary와 다른 값을 가짐) RAC처럼 매 push마다
    수집을 실행한 노드가 달라질 수 있는 경우에도 항상 같은 DB로 인식된다(WAS의 admin 서버
    호스트가 도메인의 유일 키가 아닌 것과 같은 이유 - 거긴 애초에 admin 서버가 고정이라
    asset을 키로 써도 됐지만, RAC는 대표 노드 자체가 고정이라는 보장이 없어 asset을 키에서
    완전히 뺐다). asset은 "이번 push를 실행한 노드"(WAS의 admin 서버와 같은 개념, RAC면
    push마다 다른 노드일 수 있어도 무방 - 관대한 원칙)일 뿐 DB 자체를 식별하지 않는다.

    push마다 raw_content(JSON 원문)를 통째로 교체하고(diff는 DbConfigSourceRevision으로
    감사), DB 전체 속성(open_mode/database_role 등)은 고정 컬럼으로 승격했지만 그 외
    나머지는 전부 extra에 원본 그대로 보관해 SystemHost와 동일한 패턴으로 동적 필드
    (DbConfigSourceFieldDefinition)가 코드 수정 없이 그 안에서 값을 뽑아 쓸 수 있게 한다."""

    class Kind(models.TextChoices):
        ORACLE = "oracle", "Oracle"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    # Oracle: v$database.db_unique_name. 같은 kind 안에서 유일 - RAC/Standalone/Standby
    # 전부 이 값 하나로 식별된다.
    db_unique_name = models.CharField(max_length=128)
    # 이번 push를 실행한 노드(WAS의 admin 서버 호스트와 같은 개념) - RAC는 대표 노드 1대만
    # AWX 인벤토리에 넣는 걸 권장하지만, 어느 노드가 실행하든 db_unique_name이 같으면 같은
    # 소스로 upsert되므로 이 값이 push마다 바뀌어도 안전하다. 아직 자산 미등록이면 관대한
    # 원칙으로 null.
    asset = models.ForeignKey(
        Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="db_config_sources"
    )
    db_name = models.CharField(max_length=128, blank=True)
    # PRIMARY / PHYSICAL STANDBY / LOGICAL STANDBY 등(v$database.database_role) - Data Guard
    # 구성 여부를 바로 알 수 있는 핵심 값이라 고정 컬럼으로 승격.
    database_role = models.CharField(max_length=30, blank=True)
    open_mode = models.CharField(max_length=30, blank=True)
    log_mode = models.CharField(max_length=20, blank=True)
    characterset = models.CharField(max_length=60, blank=True)
    platform_name = models.CharField(max_length=100, blank=True)
    db_created_at = models.DateTimeField(null=True, blank=True)
    # AWX가 보낸 JSON 원문 그대로(감사/재현용, DbConfigSourceRevision의 diff 대상).
    raw_content = models.TextField(blank=True)
    # raw_content를 파싱한 "database 레벨" 원본 dict 전체(instances 배열 제외) - 고정
    # 컬럼으로 승격 안 한 나머지 값(force_logging/flashback_on/cdb 등)을
    # DbConfigSourceFieldDefinition이 여기서 dot-path로 뽑는다. Oracle NCLOB 대응은
    # systems.SystemHost.extra와 동일하게 목록 화면에서 defer.
    extra = models.JSONField(default=dict, blank=True)
    # webconfig.WebConfigSource/was.WasConfigSource와 동일하게 "최근 변경일"은 저장 컬럼이
    # 아니라 대시보드 쿼리에서 revisions__detected_at의 Max로 계산한다(get_db_config_queryset).
    last_pushed_at = models.DateTimeField(auto_now=True)
    # 서비스 라벨은 기본적으로 이 DB의 인스턴스를 참조하는 JeusDataSource의 컨테이너를
    # 역추적해서 계산한다(dashboard.queries.get_service_labels_for_db_config_sources) -
    # SID가 안 맞거나 WAS가 아직 이 DB를 push 전이면 계산값이 하나도 없는 구멍이 생길 수
    # 있어, 그 구멍을 메꾸는 수기 보정값 - core.Asset.manual_services와 동일 원칙(합집합,
    # 대체 아님). DbInstance(자식)는 push마다 통짜 교체돼 직접 필드를 못 붙이므로, 안 지워지는
    # 이 상위 소스에 붙인다 - RAC라도 인스턴스 단위가 아니라 DB 전체 단위로만 보정 가능한
    # 트레이드오프(대부분 RAC 노드는 같은 서비스를 서비스하므로 실용적으로 충분).
    manual_services = models.ManyToManyField(Service, blank=True, related_name="manual_db_config_sources")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "db_unique_name"], name="unique_db_config_source"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} / {self.db_unique_name}"


class DbConfigSourceRevision(TimeStampedModel):
    """webconfig.WebConfigSourceRevision/was.WasConfigSourceRevision과 동일한 패턴 -
    raw_content가 실제로 바뀔 때만 남기는 읽기 전용 감사 이력, 승인 절차 없음."""

    source = models.ForeignKey(DbConfigSource, on_delete=models.CASCADE, related_name="revisions")
    old_content = models.TextField()
    new_content = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source} @ {self.detected_at}"


class DbInstance(TimeStampedModel):
    """인스턴스 하나(Oracle SID) = 행 하나(WAS의 JeusContainer에 대응). Standalone은
    DbConfigSource당 항상 1개, RAC는 GV$INSTANCE로 조회된 노드 수만큼. push마다 통짜
    교체한다(WebtobVhost/SystemVm과 동일 - RAC는 대표 노드 한 곳에서 GV$ 조회만으로 클러스터
    전체가 매번 다시 나오므로 diff 없이 교체가 자연스럽다). asset은 자신의 host_name으로
    별도 조회하므로 source.asset(수집 실행 노드)과 다를 수 있다(JeusContainer.asset과 동일
    이유) - 아직 미등록이면 asset=null로 두고 host_name 원본만 보존, 다음 push 때 재해석."""

    source = models.ForeignKey(DbConfigSource, on_delete=models.CASCADE, related_name="instances")
    asset = models.ForeignKey(
        Asset, null=True, blank=True, on_delete=models.SET_NULL, related_name="db_instances"
    )
    instance_name = models.CharField(max_length=30)
    instance_number = models.PositiveIntegerField(null=True, blank=True)
    # 하이퍼바이저 매칭 실패한 SystemVm.hostname과 동일 취지 - asset 매칭 실패해도 원본을
    # 화면에서 보여주기 위해 보존.
    host_name = models.CharField(max_length=255, blank=True)
    version = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, blank=True)
    archiver = models.CharField(max_length=20, blank=True)
    startup_time = models.DateTimeField(null=True, blank=True)
    # local_listener 파싱 best-effort(awx/push_oracle_config_to_cmdb.yml 참고) - 값을 못
    # 뽑으면 빈 문자열.
    listener_port = models.CharField(max_length=10, blank=True)
    # 인스턴스별 원본 전체(감사/향후 확장용) - 아직 이 레벨엔 동적 필드 정의가 없다
    # (systems.SystemVm.extra와 동일하게 필요해지면 같은 패턴을 복사해서 추가).
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "instance_name"], name="unique_db_instance_name_per_source"
            )
        ]

    def __str__(self):
        return self.instance_name


class DbConfigSourceFieldDefinition(TimeStampedModel):
    """DbConfigSource 목록 컬럼 하나 = 정의 하나 - facts.FactFieldDefinition/
    systems.SystemHostFieldDefinition과 완전히 같은 목적·구조(코드 수정 없이 admin 등록만으로
    컬럼 추가). systems와 마찬가지로 FactFieldDefinition을 재사용하지 않고 이 앱 전용으로
    둔다(값 추출 함수는 facts.dynamic_fields의 순수 함수를 그대로 재사용). FIXED는 없음 -
    DbConfigSource도 webconfig/was/systems와 동일하게 승인 절차 자체가 없어서 그 용도가
    필요 없다."""

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
            "AUTO: DbConfigSource.extra 안의 dot-path(kind_key_overrides에 없는 kind는 이 "
            "경로를 씀), 예: force_logging / MANUAL: extra와 무관한 고유 식별자"
        ),
    )
    # os_family_key_overrides(facts)/kind_key_overrides(systems)와 같은 패턴 - 지금은
    # kind=oracle 하나뿐이라 안 채워도 되지만, 나중에 다른 DB 종류가 추가돼 extra 모양이
    # 달라지는 필드가 생기면 그 kind만 채우면 된다.
    kind_key_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "AUTO 전용(선택). kind별로 key와 다른 경로를 써야 할 때만 채움. "
            '예: {"oracle": "supplemental_log_data_min"}'
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


class DbConfigSourceFieldChoice(models.Model):
    """value_type이 CHOICE인 DbConfigSourceFieldDefinition의 선택 가능한 값 - facts의
    FactFieldChoice/systems의 SystemHostFieldChoice와 동일 패턴."""

    field_definition = models.ForeignKey(
        DbConfigSourceFieldDefinition, on_delete=models.CASCADE, related_name="choices"
    )
    value = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["field_definition", "value"], name="unique_db_config_source_field_choice"
            )
        ]

    def __str__(self):
        return f"{self.field_definition.label}: {self.value}"


class DbConfigSourceFieldValue(models.Model):
    source = models.ForeignKey(DbConfigSource, on_delete=models.CASCADE, related_name="field_values")
    field_definition = models.ForeignKey(DbConfigSourceFieldDefinition, on_delete=models.CASCADE)

    value_text = models.CharField(max_length=500, null=True, blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "field_definition"], name="unique_db_config_source_field_value"
            )
        ]

    def __str__(self):
        return f"{self.source} / {self.field_definition.key}"
