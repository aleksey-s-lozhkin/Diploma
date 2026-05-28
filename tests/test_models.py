from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from documents.models import Document, SearchHistory

User = get_user_model()


class UserModelTest(TestCase):
    """Тесты кастомной логики модели User"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )

    def test_create_superuser_sets_correct_flags(self):
        """Суперпользователь создаётся с правильными флагами"""
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_email_verified)
        self.assertEqual(admin.email, "admin@example.com")

    def test_generate_verification_token(self):
        """Генерация токена подтверждения email"""
        token = self.user.generate_verification_token()
        self.assertIsNotNone(token)
        self.assertEqual(self.user.email_verification_token, token)

    def test_verify_email(self):
        """Подтверждение email активирует пользователя"""
        self.user.verify_email()
        self.assertTrue(self.user.is_email_verified)
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.email_verification_token)

    def test_generate_reset_token(self):
        """Генерация токена сброса пароля"""
        token = self.user.generate_reset_token()
        self.assertIsNotNone(token)
        self.assertEqual(self.user.reset_password_token, token)
        self.assertIsNotNone(self.user.reset_password_token_created_at)

    def test_is_reset_token_valid(self):
        """Токен сброса пароля действителен 1 час"""
        self.user.generate_reset_token()
        self.assertTrue(self.user.is_reset_token_valid())

    def test_is_reset_token_expired(self):
        """Токен сброса пароля истекает через 1 час"""
        self.user.generate_reset_token()
        self.user.reset_password_token_created_at = timezone.now() - timedelta(hours=2)
        self.user.save()
        self.assertFalse(self.user.is_reset_token_valid())

    def test_clear_reset_token(self):
        """Очистка токена сброса пароля"""
        self.user.generate_reset_token()
        self.user.clear_reset_token()
        self.assertIsNone(self.user.reset_password_token)
        self.assertIsNone(self.user.reset_password_token_created_at)

    def test_get_full_name(self):
        """Полное имя пользователя"""
        self.assertEqual(self.user.get_full_name(), "Test User")

        user_no_name = User.objects.create_user(
            email="noname@example.com",
            password="pass123",
        )
        self.assertEqual(user_no_name.get_full_name(), "noname@example.com")

    def test_str_representation(self):
        """Строковое представление пользователя"""
        self.assertEqual(str(self.user), "test@example.com")


class DocumentModelTest(TestCase):
    """Тесты кастомной логики модели Document"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )

    def test_document_str_representation(self):
        """Строковое представление документа"""
        doc = Document.objects.create(
            user=self.user,
            text="Test",
        )
        self.assertEqual(str(doc), f"Document #{doc.id}")

    def test_document_default_rubrics(self):
        """Рубрики по умолчанию"""
        doc = Document.objects.create(
            user=self.user,
            text="Test",
        )
        self.assertEqual(doc.rubrics, [])

    def test_document_default_is_public(self):
        """Публичность по умолчанию — False"""
        doc = Document.objects.create(
            user=self.user,
            text="Test",
        )
        self.assertFalse(doc.is_public)

    def test_document_tracks_original_public_status(self):
        """Документ отслеживает изменение публичности"""
        doc = Document.objects.create(
            user=self.user,
            text="Test",
            is_public=False,
        )
        self.assertEqual(doc._original_is_public, False)

        doc.is_public = True
        doc.save()
        self.assertEqual(doc._original_is_public, True)


class SearchHistoryModelTest(TestCase):
    """Тесты модели SearchHistory (documents/models.py)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )

    def test_search_history_str_representation(self):
        """Строковое представление истории поиска"""
        history = SearchHistory.objects.create(
            user=self.user,
            query="python",
        )
        self.assertEqual(str(history), f"{self.user.email}: python")
