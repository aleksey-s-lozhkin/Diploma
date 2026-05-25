from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from users.views.views_api import APILoginView, APILogoutView, APIRegisterView, APIUserProfileView

urlpatterns = [
    path("user/register/", APIRegisterView.as_view(), name="api_register"),
    path("user/login/", APILoginView.as_view(), name="api_login"),
    path("user/logout/", APILogoutView.as_view(), name="api_logout"),
    path("user/profile/", APIUserProfileView.as_view(), name="api_profile"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
]
