import bleach
from rest_framework import serializers

from .models import Document, SearchHistory

ALLOWED_TAGS = [
    "p",
    "br",
    "b",
    "i",
    "u",
    "strong",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "table",
    "tr",
    "td",
    "th",
    "thead",
    "tbody",
    "a",
    "img",
    "pre",
    "code",
    "blockquote",
    "hr",
    "div",
    "span",
]


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
        return bleach.clean(value, tags=ALLOWED_TAGS, strip=True)

    def validate_rubrics(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Рубрики должны быть списком")
        if len(value) > 10:
            raise serializers.ValidationError("Не более 10 рубрик")
        return value


class SearchHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории поиска"""

    class Meta:
        model = SearchHistory
        fields = ["id", "query", "results_count", "created_at"]
        read_only_fields = ["id", "created_at"]
