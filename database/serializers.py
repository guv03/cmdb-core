from rest_framework import serializers

from database.models import DbConfigSource


class DbConfigIngestSerializer(serializers.Serializer):
    """kind=oracle은 AWX가 sqlplus로 실행한 JSON_OBJECT/JSON_ARRAYAGG SQL의 출력(JSON
    문자열) 하나를 content로 그대로 보낸다 - webconfig/was의 content(원본 설정 텍스트)와
    동일한 자리, 이 값은 그대로 DbConfigSourceRevision의 diff 대상이자 DbConfigSource.raw_content로
    저장된다."""

    kind = serializers.ChoiceField(choices=DbConfigSource.Kind.choices)
    content = serializers.CharField()
