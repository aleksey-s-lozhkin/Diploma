from django.http import HttpResponse
from django.urls import include, path
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import views


def health_check(request):
    return HttpResponse("OK")


router = DefaultRouter()
router.register(r"documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    path("health/", health_check, name="health"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/profile/", views.UserProfileView.as_view(), name="profile"),
    path(
        "search/", cache_page(60 * 5)(vary_on_headers("Authorization")(views.SearchView.as_view())), name="api_search"
    ),
    path("", include(router.urls)),
]
