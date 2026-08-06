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

    def validate(self, attrs):
        kind = attrs.get("kind")
        if kind == WasConfigSource.Kind.JEUS6:
            if not attrs.get("files"):
                raise serializers.ValidationError(
                    {"files": "JEUS6는 files(파일명 → 원본 텍스트 dict)가 필요합니다."}
                )
        elif not attrs.get("content"):
            raise serializers.ValidationError({"content": "이 필드는 필수 항목입니다."})
        return attrs
