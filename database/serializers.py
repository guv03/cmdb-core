from rest_framework import serializers

from database.models import DbConfigSource


class DbConfigIngestSerializer(serializers.Serializer):
    """kind=oracle은 AWX가 sqlplus로 실행한 JSON_OBJECT/JSON_ARRAYAGG SQL의 출력(JSON
    문자열) 하나를 content로 그대로 보낸다 - webconfig/was의 content(원본 설정 텍스트)와
    동일한 자리, 이 값은 그대로 DbConfigSourceRevision의 diff 대상이자 DbConfigSource.raw_content로
    저장된다.

    content를 CharField가 아니라 JSONField로 받는다 - 실사용 환경에서 실측 확인된 문제:
    sqlplus 출력이 순수 JSON 텍스트라(NULL/true/false 없이 문자열·숫자만 있으면) Ansible이
    "{{ 표현식 }}" 단독 템플릿의 결과를 문자열이 아니라 Python 리터럴(dict)로 오인 변환해서
    보내는 경우가 있다(awx/push_oracle_config_to_cmdb.yml의 `| string` 필터로 근본 수정했지만,
    다른 ansible-core 버전/설정에서 재발할 수 있어 방어적으로 dict/list도 받아들인다). 정상
    케이스(문자열)는 JSONField가 그대로 통과시키므로(값을 다시 파싱하지 않음) 동작 차이 없음 -
    실제 문자열화는 database/views.py에서 처리."""

    kind = serializers.ChoiceField(choices=DbConfigSource.Kind.choices)
    content = serializers.JSONField()
