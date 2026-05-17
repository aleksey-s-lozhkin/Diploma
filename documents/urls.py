from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/profile/", views.UserProfileView.as_view(), name="profile"),
    path("ping/", views.PingView.as_view(), name="ping"),
    path("search/", views.SearchView.as_view(), name="api_search"),
]
