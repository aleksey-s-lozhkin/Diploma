from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import views

# Router для DocumentViewSet
router = DefaultRouter()
router.register(r"documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    # Health check (для Docker)
    path("health/", views.health_check, name="health_check"),
    # Аутентификация
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/profile/", views.UserProfileView.as_view(), name="profile"),
    # Документы
    path("", include(router.urls)),
    # Поиск
    path("search/", views.SearchView.as_view(), name="search"),
    path("search/history/", views.SearchHistoryView.as_view(), name="search-history"),
]
