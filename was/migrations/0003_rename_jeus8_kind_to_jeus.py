from django.db import migrations, models


def rename_jeus8_to_jeus(apps, schema_editor):
    WasConfigSource = apps.get_model("was", "WasConfigSource")
    WasConfigSource.objects.filter(kind="jeus8").update(kind="jeus")


def rename_jeus_to_jeus8(apps, schema_editor):
    WasConfigSource = apps.get_model("was", "WasConfigSource")
    WasConfigSource.objects.filter(kind="jeus").update(kind="jeus8")


class Migration(migrations.Migration):

    dependencies = [
        ('was', '0002_remove_jeuscontainer_service_name_and_more'),
    ]

    operations = [
        migrations.RunPython(rename_jeus8_to_jeus, rename_jeus_to_jeus8),
        migrations.AlterField(
            model_name='wasconfigsource',
            name='kind',
            field=models.CharField(choices=[('jeus', 'JEUS 7+')], max_length=20),
        ),
    ]
