from django.views.generic import ListView
from rest_framework.generics import ListAPIView

from dashboard.queries import build_rows, get_asset_queryset, get_dashboard_columns, get_dynamic_field_definitions
from dashboard.serializers import AssetSerializer


class AssetListView(ListView):
    template_name = "dashboard/asset_list.html"
    context_object_name = "assets"
    paginate_by = 50

    def get_queryset(self):
        return get_asset_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dynamic_field_definitions = list(get_dynamic_field_definitions())
        context["columns"] = get_dashboard_columns(self.request)
        context["rows"] = build_rows(context["assets"], dynamic_field_definitions)
        context["current_q"] = self.request.GET.get("q", "")
        return context


class AssetListAPIView(ListAPIView):
    serializer_class = AssetSerializer

    def get_queryset(self):
        return get_asset_queryset(self.request)
