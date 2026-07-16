from django.contrib.auth.views import LogoutView
from django.urls import path

from dashboard.views import (
    AssetListAPIView,
    AssetListView,
    BulkPendingChangeDecisionView,
    ChangeHistoryListView,
    DashboardLoginView,
    PendingChangeDecisionView,
)

urlpatterns = [
    path("login/", DashboardLoginView.as_view(), name="dashboard-login"),
    path("logout/", LogoutView.as_view(), name="dashboard-logout"),
    path("assets/", AssetListView.as_view(), name="dashboard-asset-list"),
    path("changes/", ChangeHistoryListView.as_view(), name="dashboard-change-history"),
    path(
        "changes/bulk-approve/",
        BulkPendingChangeDecisionView.as_view(action="approve"),
        name="dashboard-change-bulk-approve",
    ),
    path(
        "changes/bulk-reject/",
        BulkPendingChangeDecisionView.as_view(action="reject"),
        name="dashboard-change-bulk-reject",
    ),
    path(
        "changes/<int:pk>/approve/",
        PendingChangeDecisionView.as_view(action="approve"),
        name="dashboard-change-approve",
    ),
    path(
        "changes/<int:pk>/reject/",
        PendingChangeDecisionView.as_view(action="reject"),
        name="dashboard-change-reject",
    ),
]

api_urlpatterns = [
    path("assets/", AssetListAPIView.as_view(), name="api-asset-list"),
]
