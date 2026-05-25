from rest_framework import serializers

from .models import Document, SearchHistory

# Константа для максимальной длины текста
MAX_TEXT_LENGTH = 100000


class DocumentSerializer(serializers.ModelSerializer):
    """Сериализатор для документа"""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = Document
        fields = ["id", "rubrics", "text", "created_date", "is_public", "user_email", "user_id"]
        read_only_fields = ["id", "created_date", "user_email", "user_id"]


class DocumentCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания и обновления документа"""

    class Meta:
        model = Document
        fields = ["rubrics", "text", "is_public"]

    def validate_text(self, value):
        """Валидация текста без bleach"""
        if not value:
            return value

        # Проверка длины
        if len(value) > MAX_TEXT_LENGTH:
            raise serializers.ValidationError(f"Текст слишком длинный. Максимум {MAX_TEXT_LENGTH} символов.")

        # Базовая очистка: удаляем control characters
        import re

        # Удаляем нулевые символы и control characters (кроме \n, \r, \t)
        value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

        return value

    def validate_rubrics(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Рубрики должны быть списком")
        if len(value) > 10:
            raise serializers.ValidationError("Не более 10 рубрик")

        # Дополнительная валидация каждой рубрики
        for rubric in value:
            if not isinstance(rubric, str):
                raise serializers.ValidationError("Рубрики должны быть строками")
            if len(rubric) > 100:
                raise serializers.ValidationError("Рубрика не длиннее 100 символов")

        return value


class SearchHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории поиска"""

    class Meta:
        model = SearchHistory
        fields = ["id", "query", "results_count", "created_at"]
        read_only_fields = ["id", "created_at"]
