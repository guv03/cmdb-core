from django.urls import path

from webconfig.views import WebConfigIngestView

urlpatterns = [
    path("", WebConfigIngestView.as_view(), name="webconfig-ingest"),
]
