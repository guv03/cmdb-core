from django.core.management.base import BaseCommand, CommandError

from facts.dynamic_fields import coerce_fact_value, extract_json_path
from facts.models import FactFieldDefinition, HostFact, HostFactValue


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

        updated = 0
        for host_fact in HostFact.objects.all():
            raw_value = extract_json_path(host_fact.raw_facts, field_definition.key)
            defaults = coerce_fact_value(raw_value, field_definition.value_type)
            HostFactValue.objects.update_or_create(
                host_fact=host_fact, field_definition=field_definition, defaults=defaults
            )
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"{updated}개 호스트에 대해 '{field_key}' 필드를 갱신했습니다."))
