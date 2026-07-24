import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facts', '0004_alter_approvalfieldconfig_value_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='factfielddefinition',
            name='source',
            field=models.CharField(
                choices=[('auto', '자동 (raw facts 승격)'), ('manual', '수기 입력'), ('fixed', '고정 컬럼')],
                default='auto',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='factfielddefinition',
            name='key',
            field=models.CharField(
                help_text=(
                    "AUTO: raw_facts 안의 dot-path, 예: ansible_facts.ansible_memtotal_mb / "
                    "MANUAL: raw_facts와 무관한 고유 식별자 / "
                    "FIXED: HostFact 고정 컬럼명(facts.approval.FIXED_FIELD_PATHS 참고)"
                ),
                max_length=255,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name='factfielddefinition',
            name='is_visible',
            field=models.BooleanField(
                default=True, help_text="FIXED 필드는 이미 고정 컬럼으로 표시되므로 항상 꺼둘 것"
            ),
        ),
        migrations.AddField(
            model_name='factfielddefinition',
            name='requires_approval',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "켜두면 이미 존재하는 자산의 값이 push로 바뀔 때 즉시 반영하지 않고 승인 대기열에 쌓는다. "
                    "MANUAL 필드는 대상이 아님(대시보드 입력은 항상 즉시 반영)"
                ),
            ),
        ),
        migrations.AddField(
            model_name='pendingchange',
            name='field_definition',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='pending_changes',
                to='facts.factfielddefinition',
            ),
        ),
    ]
