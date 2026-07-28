import re

from processes.models import ApplicationDefinition, DetectedApplication, ProcessSnapshot


def match_one(definition: ApplicationDefinition, raw_output: str):
    """패턴이 raw_output에 매칭되면 Match 객체, 아니면 None."""
    return re.search(definition.match_pattern, raw_output, re.MULTILINE)


def resync_snapshot(snapshot: ProcessSnapshot) -> list[DetectedApplication]:
    """스냅샷 하나를 활성 정의 전체에 대해 재평가한다 - ps -ef push 시점에 사용."""
    snapshot.detected_applications.all().delete()
    matches = []
    for definition in ApplicationDefinition.objects.filter(is_active=True):
        match = match_one(definition, snapshot.raw_output)
        if match:
            matches.append(
                DetectedApplication(snapshot=snapshot, definition=definition, matched_line=match.group(0)[:1000])
            )
    DetectedApplication.objects.bulk_create(matches)
    return matches


def resync_definition(definition: ApplicationDefinition) -> None:
    """정의 하나를 기존 스냅샷 전체에 대해 재평가한다 - admin에서 정의를 등록/수정했을 때
    이미 push된 자산에도 즉시 소급 반영하기 위해 사용."""
    DetectedApplication.objects.filter(definition=definition).delete()
    if not definition.is_active:
        return

    matches = []
    for snapshot in ProcessSnapshot.objects.all():
        match = match_one(definition, snapshot.raw_output)
        if match:
            matches.append(
                DetectedApplication(snapshot=snapshot, definition=definition, matched_line=match.group(0)[:1000])
            )
    DetectedApplication.objects.bulk_create(matches)
