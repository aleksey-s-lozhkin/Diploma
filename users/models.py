import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Менеджер для кастомной модели User с аутентификацией по email."""

    def create_user(self, email, password=None, **extra_fields):
        """Создаёт и сохраняет обычного пользователя."""
        if not email:
            raise ValueError("Email обязателен")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Создаёт суперпользователя с правами администратора."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_email_verified", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Кастомная модель пользователя с аутентификацией по email и верификацией."""

    email = models.EmailField(unique=True, verbose_name="Email")
    first_name = models.CharField(max_length=30, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=30, blank=True, verbose_name="Фамилия")
    date_joined = models.DateTimeField(default=timezone.now, verbose_name="Дата регистрации")

    is_active = models.BooleanField(default=False, verbose_name="Активен")
    is_staff = models.BooleanField(default=False, verbose_name="Персонал")
    is_moderator = models.BooleanField(default=False, verbose_name="Модератор")

    # Поля для верификации email
    is_email_verified = models.BooleanField(default=False, verbose_name="Email подтверждён")
    email_verification_token = models.UUIDField(null=True, blank=True, verbose_name="Токен подтверждения email")

    # Поля для сброса пароля
    reset_password_token = models.UUIDField(null=True, blank=True, verbose_name="Токен сброса пароля")
    reset_password_token_created_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Время создания токена сброса"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        """Возвращает email пользователя."""
        return self.email

    def get_full_name(self):
        """Возвращает полное имя пользователя или email."""
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def generate_verification_token(self):
        """Генерирует UUID токен для подтверждения email."""
        self.email_verification_token = uuid.uuid4()
        self.save(update_fields=["email_verification_token"])
        return self.email_verification_token

    def verify_email(self):
        """Подтверждает email и активирует пользователя."""
        self.is_email_verified = True
        self.is_active = True
        self.email_verification_token = None
        self.save(update_fields=["is_email_verified", "is_active", "email_verification_token"])

    def generate_reset_token(self):
        """Генерирует UUID токен для сброса пароля."""
        self.reset_password_token = uuid.uuid4()
        self.reset_password_token_created_at = timezone.now()
        self.save(update_fields=["reset_password_token", "reset_password_token_created_at"])
        return self.reset_password_token

    def is_reset_token_valid(self):
        """Проверяет действителен ли токен сброса пароля (1 час)."""
        if not self.reset_password_token or not self.reset_password_token_created_at:
            return False
        delta = timezone.now() - self.reset_password_token_created_at
        return delta.total_seconds() < 3600

    def clear_reset_token(self):
        """Очищает токен сброса пароля."""
        self.reset_password_token = None
        self.reset_password_token_created_at = None
        self.save(update_fields=["reset_password_token", "reset_password_token_created_at"])
