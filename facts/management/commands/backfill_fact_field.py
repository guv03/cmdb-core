from django.core.management.base import BaseCommand, CommandError

from facts.dynamic_fields import backfill_field
from facts.models import FactFieldDefinition


class Command(BaseCommand):
    help = "새로 등록된 FactFieldDefinition을 기존 HostFact.raw_facts에서 소급 추출해 채운다."

    def add_arguments(self, parser):
        parser.add_argument("field_key", help="FactFieldDefinition.key 값")

    def handle(self, *args, **options):
        field_key = options["field_key"]
        try:
            field_definition = FactFieldDefinition.objects.get(key=field_key)
        except FactFieldDefinition.DoesNotExist:
            raise CommandError(f"필드 정의를 찾을 수 없음: {field_key}")

        if field_definition.source != FactFieldDefinition.Source.AUTO:
            raise CommandError(
                f"'{field_definition.label}'은 raw facts에서 추출하는 필드가 아니라 백필 대상이 아닙니다."
            )

        updated = backfill_field(field_definition)
        self.stdout.write(self.style.SUCCESS(f"{updated}개 호스트에 대해 '{field_key}' 필드를 갱신했습니다."))
