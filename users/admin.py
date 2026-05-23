from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = ["email", "first_name", "last_name", "is_staff", "is_moderator", "is_active", "is_email_verified"]
    list_filter = ["is_staff", "is_moderator", "is_active", "is_email_verified"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Личная информация", {"fields": ("first_name", "last_name")}),
        (
            "Права доступа",
            {"fields": ("is_active", "is_staff", "is_moderator", "is_superuser", "groups", "user_permissions")},
        ),
        ("Верификация", {"fields": ("is_email_verified", "email_verification_token")}),
        (
            "Сброс пароля",
            {"fields": ("reset_password_token", "reset_password_token_created_at"), "classes": ("collapse",)},
        ),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )

    readonly_fields = (
        "last_login",
        "date_joined",
        "email_verification_token",
        "reset_password_token",
        "reset_password_token_created_at",
    )
