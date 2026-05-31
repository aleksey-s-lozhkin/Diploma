from .views_api import APILoginView, APILogoutView, APIRegisterView, APIUserProfileView
from .views_web import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    VerifyEmailView,
)

__all__ = [
    # API views
    "APIRegisterView",
    "APILoginView",
    "APILogoutView",
    "APIUserProfileView",
    # Web views
    "LoginView",
    "RegisterView",
    "LogoutView",
    "VerifyEmailView",
    "PasswordResetRequestView",
    "PasswordResetConfirmView",
    "ChangePasswordView",
]
