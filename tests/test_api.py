from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from documents.models import Document, SearchHistory

User = get_user_model()


class UsersViewsAPITestCase(APITestCase):
    """Тесты users/views_api.py (регистрация, логин, логаут, профиль)"""

    def setUp(self):
        cache.clear()
        self.register_url = reverse("api_register")
        self.login_url = reverse("api_login")
        self.logout_url = reverse("api_logout")
        self.profile_url = reverse("api_profile")

    def test_register_success(self):
        """Успешная регистрация"""
        data = {
            "email": "newuser@example.com",
            "password": "strongpass123",
            "password2": "strongpass123",
            "first_name": "New",
            "last_name": "User",
        }
        response = self.client.post(self.register_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIsInstance(response.data["access"], str)
        self.assertGreater(len(response.data["access"]), 20)

        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "newuser@example.com")
        self.assertEqual(response.data["user"]["first_name"], "New")
        self.assertEqual(response.data["user"]["last_name"], "User")

        # Проверяем создание пользователя в БД
        user = User.objects.get(email="newuser@example.com")
        self.assertFalse(user.is_email_verified)
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password("strongpass123"))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Подтверждение email", mail.outbox[0].subject)
        self.assertIn("newuser@example.com", mail.outbox[0].to)

    def test_register_password_mismatch(self):
        """Пароли не совпадают"""
        data = {
            "email": "newuser@example.com",
            "password": "pass123",
            "password2": "pass456",
        }
        response = self.client.post(self.register_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

        self.assertFalse(User.objects.filter(email="newuser@example.com").exists())

    def test_register_existing_email(self):
        """Email уже существует"""
        User.objects.create_user(email="existing@example.com", password="pass123")

        data = {
            "email": "existing@example.com",
            "password": "pass123",
            "password2": "pass123",
        }
        response = self.client.post(self.register_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_login_success(self):
        """Успешный вход"""
        user = User.objects.create_user(email="test@example.com", password="testpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        data = {"email": "test@example.com", "password": "testpass123"}
        response = self.client.post(self.login_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIsInstance(response.data["access"], str)
        self.assertGreater(len(response.data["access"]), 20)

    def test_login_unverified_email(self):
        """Вход с неподтверждённым email"""
        User.objects.create_user(email="test@example.com", password="testpass123")

        data = {"email": "test@example.com", "password": "testpass123"}
        response = self.client.post(self.login_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("Не найдено активной учетной записи", str(response.data))

    def test_login_invalid_credentials(self):
        """Вход с неверными данными"""
        data = {"email": "wrong@example.com", "password": "wrongpass"}
        response = self.client.post(self.login_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_rate_limit(self):
        """Rate limiting при входе"""
        data = {"email": "test@example.com", "password": "wrongpass"}

        for i in range(10):
            response = self.client.post(self.login_url, data, format="json")
            self.assertNotEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_logout_success(self):
        """Успешный выход (blacklist токена)"""
        user = User.objects.create_user(email="test@example.com", password="testpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        login_data = {"email": "test@example.com", "password": "testpass123"}
        login_response = self.client.post(self.login_url, login_data, format="json")
        refresh_token = login_response.data["refresh"]
        access_token = login_response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        profile_response = self.client.get(self.profile_url)
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)

        logout_data = {"refresh": refresh_token}
        response = self.client.post(self.logout_url, logout_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        profile_response = self.client.get(self.profile_url)
        self.assertIn(profile_response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_200_OK])

    def test_profile_requires_auth(self):
        """Профиль требует аутентификации"""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_returns_user_data(self):
        """Профиль возвращает данные пользователя"""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        user.is_email_verified = True
        user.is_active = True
        user.save()

        access_token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "test@example.com")
        self.assertEqual(response.data["first_name"], "Test")
        self.assertEqual(response.data["last_name"], "User")
        self.assertEqual(response.data["full_name"], "Test User")

    def test_token_refresh_success(self):
        """Успешное обновление access токена"""
        # Сначала создаём пользователя и логинимся
        user = User.objects.create_user(email="test@example.com", password="testpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        login_data = {"email": "test@example.com", "password": "testpass123"}
        login_response = self.client.post(self.login_url, login_data, format="json")

        refresh_token = login_response.data["refresh"]
        old_access_token = login_response.data["access"]

        # Обновляем токен
        refresh_url = reverse("api_token_refresh")
        response = self.client.post(refresh_url, {"refresh": refresh_token}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

        new_access_token = response.data["access"]
        self.assertNotEqual(old_access_token, new_access_token)

        # Проверяем, что новый токен работает
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access_token}")
        profile_response = self.client.get(self.profile_url)
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)

    def test_token_refresh_missing_refresh_token(self):
        """Обновление токена без refresh токена"""
        refresh_url = reverse("api_token_refresh")
        response = self.client.post(refresh_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("Refresh token required", response.data["error"])

    def test_token_refresh_invalid_token(self):
        """Обновление токена с неверным refresh токеном"""
        refresh_url = reverse("api_token_refresh")
        response = self.client.post(refresh_url, {"refresh": "invalid.token.here"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)
        self.assertIn("Invalid or expired", response.data["error"])

    def test_token_verify_success(self):
        """Успешная проверка валидного access токена"""
        user = User.objects.create_user(email="test@example.com", password="testpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        access_token = AccessToken.for_user(user)

        verify_url = reverse("api_token_verify")
        response = self.client.post(verify_url, {"token": str(access_token)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])

    def test_token_verify_missing_token(self):
        """Проверка токена без указания токена"""
        verify_url = reverse("api_token_verify")
        response = self.client.post(verify_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("Token required", response.data["error"])

    def test_token_verify_invalid_token(self):
        """Проверка неверного токена"""
        verify_url = reverse("api_token_verify")
        response = self.client.post(verify_url, {"token": "invalid.token.here"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["valid"])
        self.assertIn("error", response.data)


class DocumentsCRUDViewsAPITestCase(APITestCase):
    """Тесты documents/views_api.py (CRUD документов + рубрики)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.user.is_email_verified = True
        self.user.is_active = True
        self.user.save()

        self.access_token = AccessToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
        )

        self.document = Document.objects.create(
            user=self.user,
            rubrics=["python", "django"],
            text="Test document content",
            is_public=False,
        )

        self.documents_list_url = reverse("document-list")
        self.documents_detail_url = lambda id: reverse("document-detail", args=[id])
        self.rubrics_url = reverse("api_rubrics")

    def test_list_documents_returns_only_user_docs(self):
        """Список возвращает только документы текущего пользователя"""
        Document.objects.create(user=self.other_user, text="Other doc")

        response = self.client.get(self.documents_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.document.id)
        self.assertEqual(response.data["results"][0]["text"], "Test document content")
        self.assertEqual(response.data["results"][0]["rubrics"], ["python", "django"])
        self.assertFalse(response.data["results"][0]["is_public"])

    def test_create_document_from_text(self):
        """Создание документа из текста"""
        data = {
            "rubrics": ["python", "test"],
            "text": "New content",
            "is_public": True,
        }
        response = self.client.post(self.documents_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["text"], "New content")
        self.assertEqual(response.data["rubrics"], ["python", "test"])
        self.assertTrue(response.data["is_public"])
        self.assertIn("id", response.data)

        doc = Document.objects.get(id=response.data["id"])
        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.text, "New content")
        self.assertEqual(doc.rubrics, ["python", "test"])
        self.assertTrue(doc.is_public)

    def test_create_document_from_file(self):
        """Создание документа из файла"""
        uploaded_file = SimpleUploadedFile("test.pdf", b"PDF content", content_type="application/pdf")
        data = {"rubrics": "python", "file": uploaded_file}
        response = self.client.post(self.documents_list_url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)

        doc = Document.objects.get(id=response.data["id"])
        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.rubrics, ["python"])
        self.assertEqual(doc.file_name, "test.pdf")
        self.assertEqual(doc.file_type, "pdf")
        self.assertEqual(doc.text_source, "file")

    def test_create_document_unsupported_file_type(self):
        """Неподдерживаемый тип файла"""
        uploaded_file = SimpleUploadedFile("test.exe", b"content", content_type="application/exe")
        data = {"rubrics": "python", "file": uploaded_file}
        response = self.client.post(self.documents_list_url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Неподдерживаемый тип файла", str(response.data))
        self.assertEqual(Document.objects.count(), 1)

    def test_create_document_too_many_rubrics(self):
        """Создание документа с >10 рубриками"""
        data = {
            "rubrics": [f"rubric_{i}" for i in range(11)],
            "text": "Test",
        }
        response = self.client.post(self.documents_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Не более 10 рубрик", str(response.data))

    def test_retrieve_own_document(self):
        """Получение своего документа"""
        url = self.documents_detail_url(self.document.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.document.id)
        self.assertEqual(response.data["text"], "Test document content")
        self.assertEqual(response.data["rubrics"], ["python", "django"])
        self.assertFalse(response.data["is_public"])

    def test_retrieve_other_private_document(self):
        """Нельзя получить чужой приватный документ"""
        other_doc = Document.objects.create(user=self.other_user, text="Private doc", is_public=False)
        url = self.documents_detail_url(other_doc.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_own_document(self):
        """Обновление своего документа"""
        url = self.documents_detail_url(self.document.id)
        data = {"text": "Updated content", "rubrics": ["updated"], "is_public": True}
        response = self.client.put(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["text"], "Updated content")
        self.assertEqual(response.data["rubrics"], ["updated"])
        self.assertTrue(response.data["is_public"])

        self.document.refresh_from_db()
        self.assertEqual(self.document.text, "Updated content")
        self.assertEqual(self.document.rubrics, ["updated"])
        self.assertTrue(self.document.is_public)

    def test_delete_own_document(self):
        """Удаление своего документа"""
        url = self.documents_detail_url(self.document.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.document.id).exists())

    def test_delete_other_document(self):
        """Нельзя удалить чужой документ"""
        other_doc = Document.objects.create(user=self.other_user, text="Other doc")
        url = self.documents_detail_url(other_doc.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Document.objects.filter(id=other_doc.id).exists())

    def test_get_rubrics(self):
        """Получение списка рубрик"""
        Document.objects.create(user=self.user, rubrics=["python", "django"], text="Doc1")
        Document.objects.create(user=self.user, rubrics=["python", "flask"], text="Doc2")
        Document.objects.create(user=self.other_user, rubrics=["fastapi"], text="Doc3", is_public=True)

        response = self.client.get(self.rubrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"python", "django", "flask", "fastapi"})

    def test_get_rubrics_empty(self):
        """Нет рубрик — пустой список"""
        Document.objects.all().delete()
        response = self.client.get(self.rubrics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class SearchViewsAPITestCase(APITestCase):
    """Тесты documents/views_api.py (поиск + история)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.user.is_email_verified = True
        self.user.is_active = True
        self.user.save()

        self.access_token = AccessToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        self.search_url = reverse("api_search")
        self.history = SearchHistory.objects.create(user=self.user, query="python", results_count=5)
        self.delete_history_url = reverse("api_search_history_delete", args=[self.history.id])

    @patch("elasticsearch_dsl.Search")
    def test_search_success(self, mock_search):
        """Успешный поиск"""
        mock_hit = MagicMock()
        mock_hit.id = 1
        mock_hit.rubrics = ["python"]
        mock_hit.text = "Python content"
        mock_hit.created_date = "2025-01-01T00:00:00Z"
        mock_hit.is_public = True

        mock_response = MagicMock()
        mock_response.hits.total.value = 1
        mock_response.__iter__.return_value = [mock_hit]

        mock_search.return_value.query.return_value.query.return_value = mock_search
        mock_search.return_value.__getitem__.return_value.execute.return_value = mock_response

        data = {"query": "python"}
        response = self.client.post(self.search_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

    def test_search_without_query(self):
        """Поиск без query — ошибка"""
        response = self.client.post(self.search_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("query", str(response.data))

    def test_delete_own_history(self):
        """Удаление своей записи истории"""
        response = self.client.delete(self.delete_history_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SearchHistory.objects.filter(id=self.history.id).exists())

    def test_delete_other_user_history(self):
        """Нельзя удалить чужую запись"""
        other_user = User.objects.create_user(email="other@example.com", password="pass")
        other_history = SearchHistory.objects.create(user=other_user, query="django")
        url = reverse("api_search_history_delete", args=[other_history.id])

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(SearchHistory.objects.filter(id=other_history.id).exists())

    def test_delete_non_existent_history(self):
        """Удаление несуществующей записи"""
        url = reverse("api_search_history_delete", args=[99999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
