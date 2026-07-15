import secrets

from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication


class ServiceUser:
    is_authenticated = True

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class StaticAPIKeyAuthentication(BaseAuthentication):
    header_name = "X-API-Key"
    settings_key_name = ""

    def authenticate(self, request):
        provided = request.headers.get(self.header_name)
        if not provided:
            return None

        expected = getattr(settings, self.settings_key_name, None)
        if not expected or not secrets.compare_digest(provided, expected):
            raise exceptions.AuthenticationFailed("Invalid API key")

        return (ServiceUser(name=self.settings_key_name), None)

    def authenticate_header(self, request):
        return self.header_name


class AWXAPIKeyAuthentication(StaticAPIKeyAuthentication):
    settings_key_name = "AWX_API_KEY"
