from django.urls import path

from users.views.views_api import (
    APILoginView,
    APILogoutView,
    APIRegisterView,
    APITokenRefreshView,
    APITokenVerifyView,
    APIUserProfileView,
)

urlpatterns = [
    path("user/register/", APIRegisterView.as_view(), name="api_register"),
    path("user/login/", APILoginView.as_view(), name="api_login"),
    path("user/logout/", APILogoutView.as_view(), name="api_logout"),
    path("user/profile/", APIUserProfileView.as_view(), name="api_profile"),
    path("user/refresh/", APITokenRefreshView.as_view(), name="api_token_refresh"),
    path("user/verify/", APITokenVerifyView.as_view(), name="api_token_verify"),
]
