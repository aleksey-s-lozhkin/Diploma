from django.urls import path
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from . import views_frontend

urlpatterns = [
    path("login/", views_frontend.LoginView.as_view(), name="login"),
    path("register/", views_frontend.RegisterView.as_view(), name="register"),
    path("logout/", views_frontend.LogoutView.as_view(), name="logout"),
    path("", cache_page(60 * 2)(vary_on_cookie(views_frontend.IndexView.as_view())), name="index"),
    path("dashboard/", views_frontend.DashboardView.as_view(), name="dashboard"),
    path("search/results/", views_frontend.SearchResultsView.as_view(), name="search_results"),
    path("search/history/", views_frontend.SearchHistoryView.as_view(), name="search_history"),
    path("search/history/clear/", views_frontend.ClearHistoryView.as_view(), name="clear_history"),
    path("documents/create/", views_frontend.DocumentCreateView.as_view(), name="document_create"),
    path("documents/<int:pk>/delete/", views_frontend.DocumentDeleteView.as_view(), name="document_delete"),
    path("documents/<int:pk>/", views_frontend.DocumentDetailView.as_view(), name="document_detail"),
    path("search/history/<int:pk>/delete/", views_frontend.DeleteHistoryItemView.as_view(), name="delete_history_item"),
    path("documents/<int:pk>/toggle-public/", views_frontend.TogglePublicView.as_view(), name="toggle_public"),
]
