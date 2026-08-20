from rest_framework import serializers

from was.models import WasConfigSource


class WasConfigIngestSerializer(serializers.Serializer):
    """kind=jeus는 파일 하나(domain.xml)라 content(단일 문자열)만 쓰지만, kind=jeus6은
    JEUSMain.xml + 컨테이너별 servlet_engine{N}/WEBMain.xml 여러 파일을 한 번에 push해야
    해서 files(파일명 → 원본 텍스트 dict)를 대신 쓴다 - 구분자로 이어붙인 문자열 대신
    구조화된 dict로 받아 파일 경계가 설정 내용과 절대 헷갈리지 않게 한다."""

    kind = serializers.ChoiceField(choices=WasConfigSource.Kind.choices)
    content = serializers.CharField(required=False, allow_blank=True)
    files = serializers.DictField(child=serializers.CharField(), required=False)
    # JEUS6 전용(WasConfigSource.instance_name 참고) - 같은 호스트에 OS 계정만 다르게 여러
    # 인스턴스가 뜰 수 있어 설정 내용만으론 구분이 안 돼 AWX가 명시적으로 실어 보낸다.
    instance_name = serializers.CharField(required=False, allow_blank=True, default="")
    # AUTO(WasConfigSource.config_path) - AWX가 이 설정을 읽어온 원본 경로(jeus6/tomcat은
    # 파일이 여러 개라 디렉터리). 없으면 기존 값을 그대로 두고 덮어쓰지 않는다(was/views.py).
    config_path = serializers.CharField(required=False, allow_blank=True)
    # Tomcat 전용 - webconfig의 apache/nginx와 동일한 이유(server.xml엔 자기 자신을 가리키는
    # 절이 없어 AWX가 inventory_hostname을 이 필드로 별도 전송해야 한다).
    hostname = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        kind = attrs.get("kind")
        if kind == WasConfigSource.Kind.JEUS6:
            if not attrs.get("files"):
                raise serializers.ValidationError(
                    {"files": "JEUS6는 files(파일명 → 원본 텍스트 dict)가 필요합니다."}
                )
            if not attrs.get("instance_name"):
                raise serializers.ValidationError(
                    {"instance_name": "JEUS6는 instance_name(OS 계정명 등 인스턴스 식별자)이 필요합니다."}
                )
        elif kind == WasConfigSource.Kind.TOMCAT:
            if not (attrs.get("files") or {}).get("server.xml"):
                raise serializers.ValidationError(
                    {"files": "Tomcat은 files에 최소 server.xml이 필요합니다(context.xml은 선택)."}
                )
            if not attrs.get("hostname"):
                raise serializers.ValidationError(
                    {"hostname": "Tomcat은 hostname 필드가 필요합니다(설정 내용만으론 호스트를 알 수 없음)."}
                )
        elif not attrs.get("content"):
            raise serializers.ValidationError({"content": "이 필드는 필수 항목입니다."})
        return attrs
