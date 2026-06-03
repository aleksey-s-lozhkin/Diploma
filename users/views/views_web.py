import logging
import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from documents.rate_limit import RateLimiters
from users.email_utils import send_password_reset_email, send_verification_email
from users.forms import ChangePasswordForm, LoginForm, PasswordResetConfirmForm, PasswordResetRequestForm, RegisterForm
from users.models import User

logger = logging.getLogger(__name__)


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        form = LoginForm()
        return render(request, "users/login.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")

        # Rate limiting по email
        email = request.POST.get("email")
        limiter = RateLimiters.login()
        allowed, remaining, retry_after = limiter.check(email)

        if not allowed:
            messages.error(request, f"Слишком много попыток входа. Попробуйте через {retry_after} секунд.")
            return render(request, "users/login.html", {"form": LoginForm()})

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
    def _redirect(self, url):
        if self.request.htmx:
            return HttpResponseClientRedirect(url)
        return redirect(url)

    def get(self, request):
        if request.user.is_authenticated:
            return self._redirect("/dashboard/")
        form = RegisterForm()
        return render(request, "users/register.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return self._redirect("/dashboard/")

        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password1"]
            first_name = form.cleaned_data.get("first_name", "").strip()
            last_name = form.cleaned_data.get("last_name", "").strip()

            # Rate limiting по email
            limiter = RateLimiters.register()
            allowed, remaining, retry_after = limiter.check(email)

            if not allowed:
                logger.warning(f"Registration rate limit exceeded for email: {email}")
                messages.error(
                    request, f"Слишком много попыток для этого email. Попробуйте через {retry_after} секунд."
                )
                if request.htmx:
                    return render(request, "users/register_form.html", {"form": form})
                return render(request, "users/register.html", {"form": form})

            # Проверка существующего пользователя
            if User.objects.filter(email=email).exists():
                logger.warning(f"Registration attempt with existing email: {email}")
                messages.error(request, "Пользователь с таким email уже существует")
                if request.htmx:
                    return render(request, "users/register_form.html", {"form": form})
                return render(request, "users/register.html", {"form": form})

            try:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True,
                    is_email_verified=False,
                )

                send_verification_email(user, request)

                logger.info(f"User registered successfully: {email}")
                messages.success(request, f"Регистрация успешна! На {email} отправлено письмо с подтверждением.")

                return self._redirect("/login/")

            except Exception as e:
                logger.error(f"Registration failed for {email}: {str(e)}")
                messages.error(request, "Произошла ошибка при регистрации. Попробуйте позже.")
                if request.htmx:
                    return render(request, "users/register_form.html", {"form": form})
                return render(request, "users/register.html", {"form": form})

        # Если форма не валидна
        if request.htmx:
            return render(request, "users/register_form.html", {"form": form})
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

        email = request.POST.get("email")

        # Rate limiting по email
        limiter = RateLimiters.password_reset()
        allowed, remaining, retry_after = limiter.check(email)

        if not allowed:
            # Не показываем ошибку, чтобы не раскрывать существование email
            messages.success(request, "Если пользователь с таким email существует, инструкции отправлены.")
            if request.htmx:
                return HttpResponseClientRedirect("/login/")
            return redirect("login")

        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            try:
                user = User.objects.get(email=email)
                send_password_reset_email(user, request)
            except User.DoesNotExist:
                # Не сообщаем, что пользователь не найден (безопасность)
                pass

            messages.success(request, f"Инструкции по сбросу пароля отправлены на {email}")

            if request.htmx:
                return HttpResponseClientRedirect("/login/")
            return redirect("login")

        if request.htmx:
            return render(request, "users/password_reset_request.html", {"form": form})
        return render(request, "users/password_reset_request.html", {"form": form})


class PasswordResetConfirmView(View):
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
