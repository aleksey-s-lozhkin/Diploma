from django.urls import path
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.vary import vary_on_cookie

from documents.views.views_web import (
    ClearHistoryView,
    DashboardView,
    DeleteHistoryItemView,
    DocumentCreateView,
    DocumentDeleteView,
    DocumentDetailView,
    GetRubricsView,
    IndexView,
    LogoutView,
    SearchHistoryView,
    SearchResultsView,
    TogglePublicView,
)

urlpatterns = [
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", cache_page(60 * 2)(vary_on_cookie(IndexView.as_view())), name="index"),
    path("dashboard/", never_cache(DashboardView.as_view()), name="dashboard"),
    path("search/results/", never_cache(SearchResultsView.as_view()), name="search_results"),
    path("search/history/", never_cache(SearchHistoryView.as_view()), name="search_history"),
    path("search/history/clear/", never_cache(ClearHistoryView.as_view()), name="clear_history"),
    path("documents/create/", never_cache(DocumentCreateView.as_view()), name="document_create"),
    path("documents/<int:pk>/delete/", never_cache(DocumentDeleteView.as_view()), name="document_delete"),
    path("documents/<int:pk>/", never_cache(DocumentDetailView.as_view()), name="document_detail"),
    path("search/history/<int:pk>/delete/", never_cache(DeleteHistoryItemView.as_view()), name="delete_history_item"),
    path("documents/<int:pk>/toggle-public/", never_cache(TogglePublicView.as_view()), name="toggle_public"),
    path("get-rubrics/", GetRubricsView.as_view(), name="get_rubrics"),
]
