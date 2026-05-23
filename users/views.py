import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from .email_utils import send_password_reset_email, send_verification_email
from .forms import ChangePasswordForm, LoginForm, PasswordResetConfirmForm, PasswordResetRequestForm, RegisterForm
from .models import User


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        form = LoginForm()
        return render(request, "users/login.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")

        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)

            if user:
                if user.is_email_verified:
                    login(request, user)
                    if request.htmx:
                        return HttpResponseClientRedirect("/dashboard/")
                    return redirect("dashboard")
                else:
                    messages.error(request, "Email не подтверждён. Проверьте свою почту.")
            else:
                messages.error(request, "Неверный email или пароль")

        if request.htmx:
            return render(request, "users/login_form.html", {"form": form})
        return render(request, "users/login.html", {"form": form})


class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")
        form = RegisterForm()
        return render(request, "users/register.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")

        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password1"]
            first_name = form.cleaned_data.get("first_name", "")
            last_name = form.cleaned_data.get("last_name", "")

            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=False,
                is_email_verified=False,
            )

            send_verification_email(user, request)

            messages.success(request, f"Регистрация успешна! На {email} отправлено письмо с подтверждением.")

            if request.htmx:
                return HttpResponseClientRedirect("/login/")
            return redirect("login")

        if request.htmx:
            return render(request, "users/register.html", {"form": form})
        return render(request, "users/register.html", {"form": form})


class LogoutView(View):
    def get(self, request):
        logout(request)
        if request.htmx:
            return HttpResponseClientRedirect("/")
        return redirect("index")


class VerifyEmailView(View):
    def get(self, request, token):
        try:
            token_uuid = uuid.UUID(token)
            user = User.objects.get(email_verification_token=token_uuid)
            user.verify_email()
            messages.success(request, "Email успешно подтверждён! Теперь вы можете войти.")
        except (ValueError, User.DoesNotExist):
            messages.error(request, "Неверная или просроченная ссылка подтверждения.")
        return redirect("login")


class PasswordResetRequestView(View):
    """Запрос на сброс пароля"""

    def get(self, request):
        if request.user.is_authenticated:
            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")
        form = PasswordResetRequestForm()
        return render(request, "users/password_reset_request.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")

        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = User.objects.get(email=email)

            send_password_reset_email(user, request)

            messages.success(request, f"Инструкции по сбросу пароля отправлены на {email}")

            if request.htmx:
                return HttpResponseClientRedirect("/login/")
            return redirect("login")

        if request.htmx:
            return render(request, "users/password_reset_request.html", {"form": form})
        return render(request, "users/password_reset_request.html", {"form": form})


class PasswordResetConfirmView(View):
    """Подтверждение сброса пароля и установка нового"""

    def get(self, request, token):
        if request.user.is_authenticated:
            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")

        try:
            user = User.objects.get(reset_password_token=token)
            if not user.is_reset_token_valid():
                messages.error(request, "Ссылка для сброса пароля истекла. Запросите новую.")
                if request.htmx:
                    return HttpResponseClientRedirect("/password-reset/")
                return redirect("password_reset_request")
        except User.DoesNotExist:
            messages.error(request, "Неверная ссылка для сброса пароля.")
            if request.htmx:
                return HttpResponseClientRedirect("/password-reset/")
            return redirect("password_reset_request")

        form = PasswordResetConfirmForm()
        return render(request, "users/password_reset_confirm.html", {"form": form, "token": token})

    def post(self, request, token):
        if request.user.is_authenticated:
            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")

        try:
            user = User.objects.get(reset_password_token=token)
            if not user.is_reset_token_valid():
                messages.error(request, "Ссылка для сброса пароля истекла. Запросите новую.")
                if request.htmx:
                    return HttpResponseClientRedirect("/password-reset/")
                return redirect("password_reset_request")
        except User.DoesNotExist:
            messages.error(request, "Неверная ссылка для сброса пароля.")
            if request.htmx:
                return HttpResponseClientRedirect("/password-reset/")
            return redirect("password_reset_request")

        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data["new_password1"]
            user.set_password(new_password)
            user.clear_reset_token()
            user.save()

            messages.success(request, "Пароль успешно изменён! Теперь вы можете войти.")

            if request.htmx:
                return HttpResponseClientRedirect("/login/")
            return redirect("login")

        if request.htmx:
            return render(request, "users/password_reset_confirm.html", {"form": form, "token": token})
        return render(request, "users/password_reset_confirm.html", {"form": form, "token": token})


@method_decorator(login_required, name="dispatch")
class ChangePasswordView(View):
    """Смена пароля авторизованным пользователем"""

    def get(self, request):
        form = ChangePasswordForm()
        return render(request, "users/change_password.html", {"form": form})

    def post(self, request):
        form = ChangePasswordForm(request.POST)
        user = request.user

        if form.is_valid():
            old_password = form.cleaned_data["old_password"]
            new_password = form.cleaned_data["new_password1"]

            if not user.check_password(old_password):
                messages.error(request, "Неверный текущий пароль")
                return render(request, "users/change_password.html", {"form": form})

            user.set_password(new_password)
            user.save()

            update_session_auth_hash(request, user)

            messages.success(request, "Пароль успешно изменён!")

            if request.htmx:
                return HttpResponseClientRedirect("/dashboard/")
            return redirect("dashboard")

        return render(request, "users/change_password.html", {"form": form})
