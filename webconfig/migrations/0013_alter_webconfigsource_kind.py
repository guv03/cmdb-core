from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webconfig', '0012_remove_apachevhost_service_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='webconfigsource',
            name='kind',
            field=models.CharField(
                choices=[('webtob', 'WEBTOB'), ('apache', 'Apache'), ('nginx', 'Nginx')], max_length=20
            ),
        ),
    ]
