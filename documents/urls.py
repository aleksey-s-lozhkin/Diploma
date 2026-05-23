from django.http import HttpResponse
from django.urls import include, path
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.vary import vary_on_headers
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import views


def health_check(request):
    return HttpResponse("OK")


router = DefaultRouter()
router.register(r"documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/logout/", never_cache(views.LogoutView.as_view()), name="logout"),
    path("auth/profile/", never_cache(views.UserProfileView.as_view()), name="profile"),
    path(
        "search/", cache_page(60 * 5)(vary_on_headers("Authorization")(views.SearchView.as_view())), name="api_search"
    ),
    path("", include(router.urls)),
]
