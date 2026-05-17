from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Document, SearchHistory


class UserSerializer(serializers.ModelSerializer):
    """Сериализатор для пользователя"""

    class Meta:
        model = User
        fields = ["id", "username", "email", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    """Сериализатор для регистрации"""

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ["username", "password", "password2", "email"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        user = User.objects.create_user(**validated_data)
        return user


class DocumentSerializer(serializers.ModelSerializer):
    """Сериализатор для документа"""

    class Meta:
        model = Document
        fields = ["id", "rubrics", "text", "created_date"]
        read_only_fields = ["id", "created_date"]


class DocumentCreateUpdateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания и обновления документа"""

    class Meta:
        model = Document
        fields = ["rubrics", "text"]


class SearchHistorySerializer(serializers.ModelSerializer):
    """Сериализатор для истории поиска"""

    class Meta:
        model = SearchHistory
        fields = ["id", "query", "results_count", "created_at"]
        read_only_fields = ["id", "created_at"]
