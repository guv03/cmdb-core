from django.urls import path

from facts.views import FactsIngestView

urlpatterns = [
    path("", FactsIngestView.as_view(), name="facts-ingest"),
]
