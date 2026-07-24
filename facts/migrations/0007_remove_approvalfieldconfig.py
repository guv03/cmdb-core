import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facts', '0006_migrate_approval_config_to_field_definition'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pendingchange',
            name='field_definition',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='pending_changes',
                to='facts.factfielddefinition',
            ),
        ),
        migrations.RemoveField(
            model_name='pendingchange',
            name='field_config',
        ),
        migrations.DeleteModel(
            name='ApprovalFieldConfig',
        ),
    ]
