from django.urls import path

from systems.views import SystemIngestView

urlpatterns = [
    path("", SystemIngestView.as_view(), name="system-ingest"),
]
