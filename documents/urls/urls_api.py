from django.urls import include, path
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from rest_framework.routers import DefaultRouter

from documents.views.views_api import DocumentViewSet, RubricsView, SearchHistoryDeleteView, SearchView

router = DefaultRouter()
router.register(r"documents", DocumentViewSet, basename="document")

urlpatterns = [
    path("search/", cache_page(60 * 5)(vary_on_headers("Authorization")(SearchView.as_view())), name="api_search"),
    path("rubrics/", RubricsView.as_view(), name="api_rubrics"),
    path("search/history/<int:pk>/", SearchHistoryDeleteView.as_view(), name="api_search_history_delete"),
    path("", include(router.urls)),
]
