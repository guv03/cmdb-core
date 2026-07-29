from rest_framework import serializers

from webconfig.models import WebConfigSource


class WebConfigIngestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=WebConfigSource.Kind.choices)
    content = serializers.CharField()
    # WebToB는 설정 내용의 *NODE절에서 hostname을 추출하지만, apache/nginx 설정 파일에는
    # 서버 자신을 가리키는 절이 없어(ServerName/server_name은 vhost 도메인일 뿐) AWX가
    # inventory_hostname을 이 필드로 별도 전송한다(webconfig/views.py의 _extract_hostname).
    hostname = serializers.CharField(required=False, allow_blank=True)
