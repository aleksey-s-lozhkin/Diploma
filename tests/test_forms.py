from django.contrib.auth import get_user_model
from django.test import TestCase

from users.forms import ChangePasswordForm, LoginForm, PasswordResetConfirmForm, PasswordResetRequestForm, RegisterForm

User = get_user_model()


class RegisterFormTest(TestCase):
    def test_valid_form(self):
        """Корректная форма регистрации"""
        form = RegisterForm(
            data={
                "email": "new@example.com",
                "password1": "strongpass123",
                "password2": "strongpass123",
                "first_name": "Test",
                "last_name": "User",
            }
        )
        self.assertTrue(form.is_valid())

    def test_password_mismatch(self):
        """Пароли не совпадают"""
        form = RegisterForm(
            data={
                "email": "new@example.com",
                "password1": "pass123",
                "password2": "pass456",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_password_too_short(self):
        """Пароль слишком короткий"""
        form = RegisterForm(
            data={
                "email": "new@example.com",
                "password1": "123",
                "password2": "123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_existing_email(self):
        """Email уже существует"""
        User.objects.create_user(email="existing@example.com", password="pass123")
        form = RegisterForm(
            data={
                "email": "existing@example.com",
                "password1": "pass123",
                "password2": "pass123",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class LoginFormTest(TestCase):
    def test_valid_form(self):
        """Корректная форма логина"""
        form = LoginForm(
            data={
                "email": "test@example.com",
                "password": "pass123",
            }
        )
        self.assertTrue(form.is_valid())

    def test_missing_email(self):
        """Отсутствует email"""
        form = LoginForm(data={"password": "pass123"})
        self.assertFalse(form.is_valid())


class PasswordResetRequestFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@example.com", password="pass123")

    def test_valid_form(self):
        """Корректная форма запроса сброса"""
        form = PasswordResetRequestForm(data={"email": "test@example.com"})
        self.assertTrue(form.is_valid())

    def test_nonexistent_email(self):
        """Email не найден"""
        form = PasswordResetRequestForm(data={"email": "nonexistent@example.com"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class PasswordResetConfirmFormTest(TestCase):
    def test_valid_form(self):
        """Корректная форма установки нового пароля"""
        form = PasswordResetConfirmForm(
            data={
                "new_password1": "newpass123",
                "new_password2": "newpass123",
            }
        )
        self.assertTrue(form.is_valid())

    def test_password_mismatch(self):
        """Пароли не совпадают"""
        form = PasswordResetConfirmForm(
            data={
                "new_password1": "pass123",
                "new_password2": "pass456",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertTrue("new_password1" in form.errors or "new_password2" in form.errors or "__all__" in form.errors)


class ChangePasswordFormTest(TestCase):
    def test_valid_form(self):
        """Корректная форма смены пароля"""
        form = ChangePasswordForm(
            data={
                "old_password": "oldpass123",
                "new_password1": "newpass123",
                "new_password2": "newpass123",
            }
        )
        self.assertTrue(form.is_valid())

    def test_new_password_mismatch(self):
        """Новые пароли не совпадают"""
        form = ChangePasswordForm(
            data={
                "old_password": "oldpass123",
                "new_password1": "pass123",
                "new_password2": "pass456",
            }
        )
        self.assertFalse(form.is_valid())
