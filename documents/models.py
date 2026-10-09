import hashlib
import secrets
from hmac import compare_digest as constant_time_compare

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Document(models.Model):
    """Модель документа пользователя"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    rubrics = models.JSONField(default=list)  # Список рубрик документа
    text = models.TextField(verbose_name="Текст документа")
    created_date = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False, verbose_name="Публичный документ")

    # Поля для загруженных файлов
    file = models.FileField(upload_to="documents/%Y/%m/%d/", blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=20, blank=True)  # pdf, docx, xlsx, txt

    TEXT_SOURCE_CHOICES = [
        ("file", "Из загруженного файла"),
        ("manual", "Ручной ввод"),
    ]
    text_source = models.CharField(
        max_length=10, choices=TEXT_SOURCE_CHOICES, default="manual", verbose_name="Источник текста"
    )

    #: Краткое описание и теги от языковой модели (documents/services/summary_service.py).
    #: Пусто, если модель недоступна: описание — украшение, а не условие работы.
    summary = models.TextField(blank=True, verbose_name="Краткое описание")
    keywords = models.JSONField(default=list, blank=True, verbose_name="Теги")

    def __str__(self):
        return f"Document #{self.id}"


class ApiToken(models.Model):
    """Токен потребителя поиска.

    Контракт (docs/SEARCH-CONTRACT.md) запрещает передавать идентификатор
    пользователя в запросе: кого искать — решает токен. Поэтому скоуп живёт
    здесь: служебный токен видит только публичные документы, персональный —
    свои и публичные.

    Хранится только хеш значения: утечка базы не даёт войти потребителям, а
    показать токен можно ровно один раз — при выпуске. Префикс остаётся
    открытым, чтобы токен можно было опознать в списке и отозвать.
    """

    SCOPE_PERSONAL = "personal"
    SCOPE_SERVICE = "service"
    SCOPE_CHOICES = [
        (SCOPE_PERSONAL, "От имени человека: свои и публичные документы"),
        (SCOPE_SERVICE, "Служебный: только публичные документы"),
    ]

    name = models.CharField(max_length=100, verbose_name="Кому выдан")
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_SERVICE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        verbose_name="Пользователь",
    )
    prefix = models.CharField(max_length=16, verbose_name="Начало значения")
    key_hash = models.CharField(max_length=64, unique=True, verbose_name="Хеш значения")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, verbose_name="Действует")

    class Meta:
        verbose_name = "Токен потребителя"
        verbose_name_plural = "Токены потребителей"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"

    def clean(self):
        """Персональный токен без человека бессмыслен: он видел бы только публичное."""
        if self.scope == self.SCOPE_PERSONAL and not self.user_id:
            raise ValidationError("Персональному токену нужен пользователь")

    @staticmethod
    def hash_value(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def matches(self, raw: str) -> bool:
        """Сравнение постоянного времени: иначе по времени ответа можно подбирать."""
        return constant_time_compare(self.key_hash, self.hash_value(raw))

    def can_read(self, document) -> bool:
        """Видны ли этому токену документ."""
        if document.is_public:
            return True
        return self.scope == self.SCOPE_PERSONAL and document.user_id == self.user_id

    @classmethod
    def issue(cls, name: str, scope: str = SCOPE_SERVICE, user=None):
        """Выпустить токен. Возвращает (токен, значение) — значение показывается один раз."""
        marker = "s" if scope == cls.SCOPE_SERVICE else "p"
        raw = f"ds_{marker}_{secrets.token_urlsafe(32)}"
        token = cls.objects.create(
            name=name,
            scope=scope,
            user=user,
            prefix=raw[:11],
            key_hash=cls.hash_value(raw),
        )
        return token, raw


class SearchHistory(models.Model):
    """Модель истории поисковых запросов пользователя"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_history")
    query = models.CharField(max_length=500)  # Поисковый запрос
    results_count = models.IntegerField(default=0)  # Количество найденных результатов
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email}: {self.query}"
