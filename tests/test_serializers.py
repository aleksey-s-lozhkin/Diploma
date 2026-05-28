from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.serializers import DocumentCreateUpdateSerializer, DocumentSerializer, SearchHistorySerializer
from users.serializers import RegisterSerializer, UserSerializer

User = get_user_model()


class UserSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )

    def test_serializer_contains_expected_fields(self):
        """Проверка полей сериализатора UserSerializer"""
        serializer = UserSerializer(self.user)
        data = serializer.data
        expected_fields = {"id", "email", "first_name", "last_name", "full_name", "date_joined", "is_moderator"}
        self.assertEqual(set(data.keys()), expected_fields)

    def test_full_name_field(self):
        """Поле full_name возвращает полное имя"""
        serializer = UserSerializer(self.user)
        self.assertEqual(serializer.data["full_name"], "Test User")

    def test_full_name_fallback_to_email(self):
        """Если нет имени, full_name возвращает email"""
        user_no_name = User.objects.create_user(
            email="nofullname@example.com",
            password="pass123",
        )
        serializer = UserSerializer(user_no_name)
        self.assertEqual(serializer.data["full_name"], "nofullname@example.com")


class RegisterSerializerTest(TestCase):
    def test_valid_data(self):
        """Корректные данные для регистрации"""
        data = {
            "email": "new@example.com",
            "password": "strongpass123",
            "password2": "strongpass123",
            "first_name": "New",
            "last_name": "User",
        }
        serializer = RegisterSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_password_mismatch(self):
        """Пароли не совпадают"""
        data = {
            "email": "new@example.com",
            "password": "pass123",
            "password2": "pass456",
        }
        serializer = RegisterSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)

    def test_existing_email(self):
        """Email уже существует"""
        User.objects.create_user(email="existing@example.com", password="pass123")
        data = {
            "email": "existing@example.com",
            "password": "pass123",
            "password2": "pass123",
        }
        serializer = RegisterSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

    def test_create_user(self):
        """Создание пользователя через сериализатор"""
        data = {
            "email": "new@example.com",
            "password": "strongpass123",
            "password2": "strongpass123",
            "first_name": "New",
            "last_name": "User",
        }
        serializer = RegisterSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "User")
        self.assertTrue(user.check_password("strongpass123"))


class DocumentSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.document = self.user.documents.create(
            rubrics=["python", "django"],
            text="Test content",
            is_public=False,
        )

    def test_serializer_contains_expected_fields(self):
        """Проверка полей сериализатора DocumentSerializer"""
        serializer = DocumentSerializer(self.document)
        data = serializer.data
        expected_fields = {"id", "rubrics", "text", "created_date", "is_public", "user_email", "user_id"}
        self.assertEqual(set(data.keys()), expected_fields)


class DocumentCreateUpdateSerializerTest(TestCase):
    def test_validate_text_too_long(self):
        """Слишком длинный текст"""
        serializer = DocumentCreateUpdateSerializer(
            data={
                "text": "a" * 100001,
                "rubrics": [],
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("text", serializer.errors)

    def test_validate_rubrics_not_list(self):
        """Рубрики должны быть списком"""
        serializer = DocumentCreateUpdateSerializer(
            data={
                "text": "test",
                "rubrics": "not a list",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rubrics", serializer.errors)

    def test_validate_rubrics_too_many(self):
        """Не более 10 рубрик"""
        serializer = DocumentCreateUpdateSerializer(
            data={
                "text": "test",
                "rubrics": [f"rubric_{i}" for i in range(11)],
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rubrics", serializer.errors)

    def test_validate_rubric_too_long(self):
        """Рубрика не длиннее 100 символов"""
        serializer = DocumentCreateUpdateSerializer(
            data={
                "text": "test",
                "rubrics": ["a" * 101],
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rubrics", serializer.errors)

    def test_validate_rubric_not_string(self):
        """Рубрики должны быть строками"""
        serializer = DocumentCreateUpdateSerializer(
            data={
                "text": "test",
                "rubrics": [1, 2, 3],
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("rubrics", serializer.errors)

    def test_valid_data(self):
        """Корректные данные"""
        serializer = DocumentCreateUpdateSerializer(
            data={
                "text": "Normal text",
                "rubrics": ["python", "django"],
                "is_public": True,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class SearchHistorySerializerTest(TestCase):
    def test_serializer_fields(self):
        """Проверка полей сериализатора истории поиска"""
        serializer = SearchHistorySerializer()
        expected_fields = {"id", "query", "results_count", "created_at"}
        self.assertEqual(set(serializer.fields.keys()), expected_fields)
