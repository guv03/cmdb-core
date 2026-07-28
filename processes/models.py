import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe

from core.models import Asset, TimeStampedModel

# admin에서 정규식을 처음 등록하는 사람이 참고할 수 있게 실제로 쓸 법한 패턴 예시를 help_text에
# 같이 보여준다(admin은 field.help_text를 |safe로 그대로 렌더링하므로 <br>/<code>가 그대로 먹힘).
MATCH_PATTERN_HELP_TEXT = mark_safe(
    "ps -ef 원본 전체에 대한 정규식(re.search). 예시:<br>"
    "· <code>postgres</code> — PostgreSQL 관련 프로세스(특수문자 없으면 단순 포함 검색과 동일하게 동작)<br>"
    "· <code>jeus\\.server\\.JEUSBooter</code> — JEUS 부트 클래스(마침표는 정규식에서 \"아무 문자나\"라 "
    "리터럴 점을 매칭하려면 <code>\\.</code>로 이스케이프)<br>"
    "· <code>ora_pmon_\\w+</code> — Oracle DB 인스턴스의 pmon 프로세스(인스턴스명은 SID마다 달라 "
    "<code>\\w+</code>로 아무 값이나 허용)<br>"
    "· <code>/app/webtob/bin/wsmond</code> — 특정 실행 경로 그대로(정규식 특수문자가 없으면 경로 문자열 자체를 써도 됨)"
)


class ApplicationDefinition(TimeStampedModel):
    """관리자가 등록하는 정규식 패턴. ps -ef 원본에 매칭되면 해당 어플리케이션이 동작 중이라고
    판단한다 - 코드 수정 없이 admin에서 패턴만 추가/수정하면 되는 구조(FactFieldDefinition과
    동일 취지)."""

    name = models.CharField(max_length=100, unique=True)
    match_pattern = models.CharField(max_length=255, help_text=MATCH_PATTERN_HELP_TEXT)
    is_active = models.BooleanField(default=True)

    def clean(self):
        try:
            re.compile(self.match_pattern)
        except re.error as exc:
            raise ValidationError({"match_pattern": f"올바른 정규식이 아닙니다: {exc}"})

    def __str__(self):
        return self.name


class ProcessSnapshot(TimeStampedModel):
    """자산별 최신 ps -ef 원본. push마다 통짜 교체 - 프로세스는 PID 등이 수시로 바뀌어 이전
    push와의 diff를 남기는 게 무의미하므로(webconfig의 WebConfigSourceRevision과 달리)
    이력 없이 최신 스냅샷만 유지한다."""

    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="process_snapshot")
    raw_output = models.TextField()
    collected_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.asset.hostname} ps -ef"


class DetectedApplication(TimeStampedModel):
    """스냅샷 하나에서 매칭된 어플리케이션 - push(또는 admin에서의 정의 등록/수정) 시점마다
    통짜 재생성(webconfig의 구조화 테이블과 동일 패턴)."""

    snapshot = models.ForeignKey(ProcessSnapshot, on_delete=models.CASCADE, related_name="detected_applications")
    definition = models.ForeignKey(ApplicationDefinition, on_delete=models.CASCADE, related_name="detections")
    matched_line = models.CharField(max_length=1000, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["snapshot", "definition"], name="unique_app_per_snapshot")
        ]

    def __str__(self):
        return f"{self.snapshot.asset.hostname} / {self.definition.name}"
