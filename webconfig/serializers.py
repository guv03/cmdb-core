from rest_framework import serializers

from webconfig.models import WebConfigSource


class WebConfigIngestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=WebConfigSource.Kind.choices)
    content = serializers.CharField()
    # WebToB는 설정 내용의 *NODE절에서 hostname을 추출하지만, apache/nginx 설정 파일에는
    # 서버 자신을 가리키는 절이 없어(ServerName/server_name은 vhost 도메인일 뿐) AWX가
    # inventory_hostname을 이 필드로 별도 전송한다(webconfig/views.py의 _extract_hostname).
    hostname = serializers.CharField(required=False, allow_blank=True)
    # AUTO(WebConfigSource.config_path) - AWX가 이 설정을 읽어온 원본 파일 경로. 없으면
    # (아직 role 업데이트 전 자산) 기존 값을 그대로 두고 덮어쓰지 않는다(webconfig/views.py).
    config_path = serializers.CharField(required=False, allow_blank=True)
