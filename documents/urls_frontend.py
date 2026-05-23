from django.urls import path
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.vary import vary_on_cookie

from . import views_frontend

urlpatterns = [
    path("logout/", views_frontend.LogoutView.as_view(), name="logout"),
    path("", cache_page(60 * 2)(vary_on_cookie(views_frontend.IndexView.as_view())), name="index"),
    path("dashboard/", never_cache(views_frontend.DashboardView.as_view()), name="dashboard"),
    path("search/results/", never_cache(views_frontend.SearchResultsView.as_view()), name="search_results"),
    path("search/history/", never_cache(views_frontend.SearchHistoryView.as_view()), name="search_history"),
    path("search/history/clear/", never_cache(views_frontend.ClearHistoryView.as_view()), name="clear_history"),
    path("documents/create/", never_cache(views_frontend.DocumentCreateView.as_view()), name="document_create"),
    path(
        "documents/<int:pk>/delete/", never_cache(views_frontend.DocumentDeleteView.as_view()), name="document_delete"
    ),
    path("documents/<int:pk>/", never_cache(views_frontend.DocumentDetailView.as_view()), name="document_detail"),
    path(
        "search/history/<int:pk>/delete/",
        never_cache(views_frontend.DeleteHistoryItemView.as_view()),
        name="delete_history_item",
    ),
    path(
        "documents/<int:pk>/toggle-public/",
        never_cache(views_frontend.TogglePublicView.as_view()),
        name="toggle_public",
    ),
    path("get-rubrics/", views_frontend.GetRubricsView.as_view(), name="get_rubrics"),
]
