from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('was', '0003_rename_jeus8_kind_to_jeus'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wasconfigsource',
            name='kind',
            field=models.CharField(choices=[('jeus', 'JEUS')], max_length=20),
        ),
    ]
