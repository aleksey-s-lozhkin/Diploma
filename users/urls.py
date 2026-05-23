from django.urls import path

from . import api_views, views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    # API endpoints
    path("api/register/", api_views.APIRegisterView.as_view(), name="api_register"),
    path("api/logout/", api_views.APILogoutView.as_view(), name="api_logout"),
    path("api/profile/", api_views.APIUserProfileView.as_view(), name="api_profile"),
]
