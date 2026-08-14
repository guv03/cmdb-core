from django.urls import path

from database.views import DbConfigIngestView

urlpatterns = [
    path("", DbConfigIngestView.as_view(), name="database-ingest"),
]
