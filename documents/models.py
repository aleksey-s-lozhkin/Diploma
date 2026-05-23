from django.conf import settings
from django.db import models


class Document(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    rubrics = models.JSONField(default=list)
    text = models.TextField(verbose_name="Текст документа")
    created_date = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False, verbose_name="Публичный документ")

    # Поля для файлов
    file = models.FileField(upload_to="documents/%Y/%m/%d/", blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=20, blank=True)

    TEXT_SOURCE_CHOICES = [
        ("file", "Из загруженного файла"),
        ("manual", "Ручной ввод"),
    ]
    text_source = models.CharField(
        max_length=10, choices=TEXT_SOURCE_CHOICES, default="manual", verbose_name="Источник текста"
    )

    def __str__(self):
        return f"Document #{self.id}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "is_public"):
            self._original_is_public = self.is_public
        else:
            self._original_is_public = False

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Обновляем исходное состояние после сохранения
        self._original_is_public = self.is_public


class SearchHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_history")
    query = models.CharField(max_length=500)
    results_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email}: {self.query}"
