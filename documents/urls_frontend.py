from django.urls import path

from . import views_frontend

urlpatterns = [
    # Аутентификация
    path("login/", views_frontend.login_view, name="login"),
    path("register/", views_frontend.register_view, name="register"),
    path("logout/", views_frontend.logout_view, name="logout"),
    # Основные страницы
    path("", views_frontend.index, name="index"),
    path("dashboard/", views_frontend.dashboard, name="dashboard"),
    # Поиск (HTMX)
    path("search/results/", views_frontend.search_results, name="search_results"),
    path("search/history/", views_frontend.search_history, name="search_history"),
    path("search/history/clear/", views_frontend.clear_history, name="clear_history"),
    # Документы
    path("documents/create/", views_frontend.document_create, name="document_create"),
    path("documents/<int:pk>/edit/", views_frontend.document_edit, name="document_edit"),
    path("documents/<int:pk>/delete/", views_frontend.document_delete, name="document_delete"),
]
