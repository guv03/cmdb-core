from django.contrib import admin
from django.urls import include, path

from dashboard.urls import api_urlpatterns as dashboard_api_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/facts/", include("facts.urls")),
    path("api/webconfig/", include("webconfig.urls")),
    path("api/", include("core.urls")),
    path("api/", include(dashboard_api_urlpatterns)),
    path("dashboard/", include("dashboard.urls")),
]
