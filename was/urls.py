from django.urls import path

from was.views import WasConfigIngestView

urlpatterns = [
    path("", WasConfigIngestView.as_view(), name="was-ingest"),
]
