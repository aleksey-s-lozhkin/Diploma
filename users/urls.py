from django.urls import path

from . import api_views, views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("verify-email/<str:token>/", views.VerifyEmailView.as_view(), name="verify_email"),
    # Восстановление пароля
    path("password-reset/", views.PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("password-reset/<str:token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change_password"),
    # API endpoints
    path("api/register/", api_views.APIRegisterView.as_view(), name="api_register"),
    path("api/logout/", api_views.APILogoutView.as_view(), name="api_logout"),
    path("api/profile/", api_views.APIUserProfileView.as_view(), name="api_profile"),
]
