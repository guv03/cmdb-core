from django.urls import path

from dashboard.views import AssetListAPIView, AssetListView

urlpatterns = [
    path("assets/", AssetListView.as_view(), name="dashboard-asset-list"),
]

api_urlpatterns = [
    path("assets/", AssetListAPIView.as_view(), name="api-asset-list"),
]
