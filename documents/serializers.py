import re

from rest_framework import serializers

from .constants import MAX_TEXT_LENGTH, DocumentValidationError, normalize_rubrics
from .models import Document, SearchHistory


class DocumentSerializer(serializers.ModelSerializer):
    """Сериализатор для документа (чтение)"""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "rubrics",
            "text",
            "created_date",
            "is_public",
            # Поля загруженного файла раньше не отдавались: клиент не мог узнать,
            # из какого файла получен документ и как его скачать.
            "file",
            "file_name",
            "file_type",
            "text_source",
            "user_email",
            "user_id",
        ]
        read_only_fields = [
            "id",
            "created_date",
            "file",
            "file_name",
            "file_type",
            "text_source",
            "user_email",
            "user_id",
        ]


class DocumentCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания и обновления документа"""

    class Meta:
        model = Document
        fields = ["rubrics", "text", "is_public"]

    def validate_text(self, value):
        """Валидация текста: длина и удаление control characters"""
        if not value:
            return value

        # Проверка максимальной длины
        if len(value) > MAX_TEXT_LENGTH:
            raise serializers.ValidationError(f"Текст слишком длинный. Максимум {MAX_TEXT_LENGTH} символов.")

        # Базовая очистка: удаляем control characters (оставляем \n, \r, \t)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

        return value

    def validate_rubrics(self, value):
        """Валидация рубрик общими правилами из documents/constants.py"""
        try:
            return normalize_rubrics(value)
        except DocumentValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class SearchHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории поиска (только чтение)"""

    class Meta:
        model = SearchHistory
        fields = ["id", "query", "results_count", "created_at"]
        read_only_fields = ["id", "created_at"]
