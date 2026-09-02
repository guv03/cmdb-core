import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """JeusContainer/JeusDataSource -> WasContainer/WasDataSource 이름 정리. 이 두 모델은
    kind=jeus/jeus6뿐 아니라 tomcat도 그대로 담는 kind 무관 공용 모델인데 이름이 JEUS
    전용인 것처럼 보여 혼동을 준다는 지적으로 개명(CLAUDE.md "WAS 설정" 참고). RenameModel +
    related_name 정리용 AlterField만 있고 실제 컬럼/데이터 변화는 없다(테이블 RENAME과
    제약조건 재생성뿐 - Postgres/Oracle 둘 다 표준 SQL이라 안전).

    사용자가 대시보드에서 "JEUS 컨테이너" 목록을 쓰다가 톰캣 컨테이너까지 같은 모델에
    섞여 들어가는 걸 보고 이름이 잘못됐다고 지적한 게 계기 - kind별 화면(JeusContainerListView/
    TomcatContainerListView, get_jeus_container_queryset 등)은 실제로 kind로 필터링해서
    보여주는 이름 그대로라 안 건드렸고, kind 무관 공용 모델/related_name/필드만 정리했다.

    `JeusWebtobConnector`는 이 개명 대상에서 뺐다 - WasContainer/WasDataSource와 달리
    Tomcat 컨테이너에서는 이 모델에 행이 절대 안 생긴다(was/parsers.py의 parse_tomcat이
    webtob_connectors를 항상 빈 리스트로 반환). kind 무관 공용 모델이 아니라 순수
    JEUS/JEUS6 전용 개념이라 이름 그대로 두는 게 맞다는 지적으로 처음 초안에서 되돌림.
    """

    dependencies = [
        ("core", "0002_asset_last_changed_at"),
        ("database", "0002_dbconfigsource_manual_services"),
        ("network", "0001_initial"),
        ("was", "0011_jeuscontainer_manual_db_sources_and_more"),
    ]

    operations = [
        migrations.RenameModel(old_name="JeusContainer", new_name="WasContainer"),
        migrations.RenameModel(old_name="JeusDataSource", new_name="WasDataSource"),
        migrations.AlterField(
            model_name="wascontainer",
            name="asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="was_containers",
                to="core.asset",
            ),
        ),
        migrations.AlterField(
            model_name="wascontainer",
            name="service",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="was_containers",
                to="core.service",
            ),
        ),
        migrations.AlterField(
            model_name="wascontainer",
            name="manual_routes",
            field=models.ManyToManyField(blank=True, related_name="was_containers", to="network.networkroute"),
        ),
        migrations.AlterField(
            model_name="wascontainer",
            name="manual_db_sources",
            field=models.ManyToManyField(
                blank=True, related_name="manual_was_containers", to="database.dbconfigsource"
            ),
        ),
        migrations.AlterField(
            model_name="wasdatasource",
            name="db_instance",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="was_data_sources",
                to="database.dbinstance",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="wascontainer",
            name="unique_jeus_container_name_per_source",
        ),
        migrations.AddConstraint(
            model_name="wascontainer",
            constraint=models.UniqueConstraint(fields=("source", "name"), name="unique_was_container_name_per_source"),
        ),
        migrations.RemoveConstraint(
            model_name="wasdatasource",
            name="unique_jeus_datasource_per_source",
        ),
        migrations.AddConstraint(
            model_name="wasdatasource",
            constraint=models.UniqueConstraint(
                fields=("source", "data_source_id"), name="unique_was_datasource_per_source"
            ),
        ),
    ]
