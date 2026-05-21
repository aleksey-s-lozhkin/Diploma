from django.contrib.auth.models import User
from django.db import models


class Document(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
    rubrics = models.JSONField(default=list)
    text = models.TextField(verbose_name="Текст документа (HTML)")
    created_date = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False, verbose_name="Публичный документ")

    # Поля для файлов
    file = models.FileField(upload_to="documents/%Y/%m/%d/", blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Document #{self.id}"


class SearchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="search_history")
    query = models.CharField(max_length=500)
    results_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}: {self.query}"
