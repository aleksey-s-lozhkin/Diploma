from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views import View

from .forms import LoginForm, RegisterForm
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
                login(request, user)
                return redirect("dashboard")
            else:
                messages.error(request, "Неверный email или пароль")

        return render(request, "users/login.html", {"form": form})


class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        form = RegisterForm()
        return render(request, "users/register.html", {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")

        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password1"]
            first_name = form.cleaned_data.get("first_name", "")
            last_name = form.cleaned_data.get("last_name", "")

            User.objects.create_user(email=email, password=password, first_name=first_name, last_name=last_name)

            messages.success(request, "Регистрация успешна! Теперь вы можете войти.")
            return redirect("login")

        return render(request, "users/register.html", {"form": form})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("index")
