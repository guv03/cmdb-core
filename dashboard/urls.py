from django.contrib.auth.views import LogoutView
from django.urls import path

from dashboard.views import (
    AssetFactsDetailView,
    AssetListAPIView,
    AssetListView,
    AssetManualFieldUpdateView,
    BulkPendingChangeDecisionView,
    ChangeHistoryListView,
    DashboardLoginView,
    ManualFieldImportConfirmView,
    ManualFieldImportView,
    PendingChangeDecisionView,
    WebConfigDetailView,
    WebConfigListView,
)

urlpatterns = [
    path("login/", DashboardLoginView.as_view(), name="dashboard-login"),
    path("logout/", LogoutView.as_view(), name="dashboard-logout"),
    path("assets/", AssetListView.as_view(), name="dashboard-asset-list"),
    path("assets/<int:pk>/facts/", AssetFactsDetailView.as_view(), name="dashboard-asset-facts"),
    path(
        "assets/<int:pk>/manual-fields/",
        AssetManualFieldUpdateView.as_view(),
        name="dashboard-asset-manual-fields-update",
    ),
    path("assets/import/", ManualFieldImportView.as_view(), name="dashboard-asset-import"),
    path(
        "assets/import/confirm/",
        ManualFieldImportConfirmView.as_view(),
        name="dashboard-asset-import-confirm",
    ),
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
    path("webconfig/", WebConfigListView.as_view(), name="dashboard-webconfig-list"),
    path("webconfig/<int:pk>/", WebConfigDetailView.as_view(), name="dashboard-webconfig-detail"),
]

api_urlpatterns = [
    path("assets/", AssetListAPIView.as_view(), name="api-asset-list"),
]
