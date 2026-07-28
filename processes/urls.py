from django.urls import path

from processes.views import ProcessIngestView

urlpatterns = [
    path("", ProcessIngestView.as_view(), name="processes-ingest"),
]
