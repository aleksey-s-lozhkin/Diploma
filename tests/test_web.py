from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from documents.models import Document, SearchHistory

User = get_user_model()


class WebAuthTest(TestCase):
    """Тесты users/views_web.py (регистрация, логин, сброс пароля)"""

    def setUp(self):
        cache.clear()
        self.register_url = reverse("register")
        self.login_url = reverse("login")
        self.logout_url = reverse("logout")
        self.password_reset_request_url = reverse("password_reset_request")

    def test_register_page_loads(self):
        """Страница регистрации загружается"""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")
        self.assertContains(response, "Регистрация")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_register_success(self):
        """Успешная регистрация"""
        data = {
            "email": "newuser@example.com",
            "password1": "strongpass123",
            "password2": "strongpass123",
            "first_name": "New",
            "last_name": "User",
        }
        response = self.client.post(self.register_url, data)

        # Проверяем редирект на страницу логина
        self.assertRedirects(response, "/login/")

        # Проверяем создание пользователя в БД
        user = User.objects.get(email="newuser@example.com")
        self.assertFalse(user.is_email_verified)
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "User")
        self.assertTrue(user.check_password("strongpass123"))

        # Проверяем отправку письма
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Подтверждение email", mail.outbox[0].subject)
        self.assertIn("newuser@example.com", mail.outbox[0].to)
        self.assertIn("Подтвердить email", mail.outbox[0].body)

    def test_register_existing_email(self):
        """Регистрация с существующим email"""
        User.objects.create_user(email="existing@example.com", password="pass123")

        data = {
            "email": "existing@example.com",
            "password1": "pass123",
            "password2": "pass123",
        }
        response = self.client.post(self.register_url, data, follow=True)

        # Проверяем, что пользователь не создался повторно
        self.assertEqual(User.objects.filter(email="existing@example.com").count(), 1)
        # Проверяем, что остались на странице регистрации (не редирект)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")

    def test_register_password_mismatch(self):
        """Пароли не совпадают"""
        data = {
            "email": "newuser@example.com",
            "password1": "pass123",
            "password2": "pass456",
        }
        response = self.client.post(self.register_url, data, follow=True)

        # Проверяем, что пользователь не создался
        self.assertFalse(User.objects.filter(email="newuser@example.com").exists())
        # Проверяем, что остались на странице регистрации
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/register.html")

    def test_login_page_loads(self):
        """Страница входа загружается"""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/login.html")
        self.assertContains(response, "Вход в систему")

    def test_login_success(self):
        """Успешный вход"""
        user = User.objects.create_user(email="test@example.com", password="testpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        data = {"email": "test@example.com", "password": "testpass123"}
        response = self.client.post(self.login_url, data)

        # Проверяем редирект на дашборд
        self.assertRedirects(response, "/dashboard/")

        # Проверяем, что пользователь действительно авторизован
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.email, "test@example.com")

    def test_login_unverified_email(self):
        """Вход с неподтверждённым email"""
        User.objects.create_user(email="test@example.com", password="testpass123")

        data = {"email": "test@example.com", "password": "testpass123"}
        response = self.client.post(self.login_url, data, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверный email или пароль")

        # Проверяем, что пользователь не авторизован
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_invalid_credentials(self):
        """Вход с неверными данными"""
        data = {"email": "wrong@example.com", "password": "wrongpass"}
        response = self.client.post(self.login_url, data, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверный email или пароль")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout(self):
        """Выход из системы"""
        user = User.objects.create_user(email="test@example.com", password="testpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        # Сначала логинимся
        self.client.login(email="test@example.com", password="testpass123")

        # Проверяем, что авторизованы
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)

        # Выход
        response = self.client.get(self.logout_url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

        # Проверяем, что больше не авторизованы
        response = self.client.get("/dashboard/")
        self.assertRedirects(response, "/login/?next=/dashboard/")

    def test_verify_email(self):
        """Подтверждение email по токену"""
        user = User.objects.create_user(email="test@example.com", password="pass123")
        token = user.generate_verification_token()

        verify_url = reverse("verify_email", args=[token])
        response = self.client.get(verify_url)

        # Проверяем редирект на логин
        self.assertRedirects(response, "/login/")

        # Проверяем, что email подтверждён
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertTrue(user.is_active)
        self.assertIsNone(user.email_verification_token)

    def test_verify_email_invalid_token(self):
        """Подтверждение email с неверным токеном"""
        verify_url = reverse("verify_email", args=["invalid-token"])
        response = self.client.get(verify_url)

        self.assertRedirects(response, "/login/")

        # Проверяем сообщение через messages
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("Неверная или просроченная ссылка" in str(m) for m in messages))

    def test_password_reset_request_success(self):
        """Успешный запрос сброса пароля"""
        User.objects.create_user(email="test@example.com", password="oldpass")

        data = {"email": "test@example.com"}
        response = self.client.post(self.password_reset_request_url, data)

        self.assertRedirects(response, "/login/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Сброс пароля", mail.outbox[0].subject)
        self.assertIn("test@example.com", mail.outbox[0].to)

    def test_password_reset_confirm_success(self):
        """Успешное подтверждение сброса пароля"""
        user = User.objects.create_user(email="test@example.com", password="oldpass")
        token = user.generate_reset_token()

        confirm_url = reverse("password_reset_confirm", args=[token])
        data = {
            "new_password1": "newpass123",
            "new_password2": "newpass123",
        }
        response = self.client.post(confirm_url, data)

        # Проверяем редирект на логин
        self.assertRedirects(response, "/login/")

        # Проверяем, что пароль изменился
        user.refresh_from_db()
        self.assertTrue(user.check_password("newpass123"))
        self.assertIsNone(user.reset_password_token)
        self.assertIsNone(user.reset_password_token_created_at)

    def test_change_password_success(self):
        """Успешная смена пароля авторизованным пользователем"""
        user = User.objects.create_user(email="test@example.com", password="oldpass123")
        user.is_email_verified = True
        user.is_active = True
        user.save()

        self.client.login(email="test@example.com", password="oldpass123")

        change_password_url = reverse("change_password")
        data = {
            "old_password": "oldpass123",
            "new_password1": "newpass123",
            "new_password2": "newpass123",
        }
        response = self.client.post(change_password_url, data)

        self.assertRedirects(response, "/dashboard/")

        # Проверяем, что пароль изменился
        user.refresh_from_db()
        self.assertTrue(user.check_password("newpass123"))

        # Проверяем, что можно войти с новым паролем
        self.client.logout()
        login_success = self.client.login(email="test@example.com", password="newpass123")
        self.assertTrue(login_success)


class WebDocumentsTest(TestCase):
    """Тесты documents/views_web.py (дашборд, создание документов, история)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.user.is_email_verified = True
        self.user.is_active = True
        self.user.save()

        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
        )

        self.client.login(email="test@example.com", password="testpass123")

        self.dashboard_url = reverse("dashboard")
        self.document_create_url = reverse("document_create")
        self.search_history_url = reverse("search_history")
        self.clear_history_url = reverse("clear_history")

    def test_dashboard_page_loads(self):
        """Страница дашборда загружается"""
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard.html")
        self.assertContains(response, "Мои документы")
        self.assertContains(response, "Создать документ")

    def test_dashboard_shows_only_user_docs(self):
        """Дашборд показывает только свои документы"""
        Document.objects.create(user=self.user, text="My document")
        Document.objects.create(user=self.other_user, text="Other document")

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, "My document")
        self.assertNotContains(response, "Other document")

    def test_dashboard_shows_public_docs_when_toggled(self):
        """Дашборд показывает публичные документы при переключении"""
        Document.objects.create(user=self.user, text="My private", is_public=False)
        Document.objects.create(user=self.other_user, text="Other public", is_public=True)

        response = self.client.get(self.dashboard_url, {"show_public": "true"})

        self.assertContains(response, "My private")
        self.assertContains(response, "Other public")

    def test_document_create_page_loads(self):
        """Страница создания документа загружается"""
        response = self.client.get(self.document_create_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "document_form.html")
        self.assertContains(response, "Новый документ")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_document_create_from_text(self):
        """Создание документа из текста"""
        data = {
            "rubrics": "python, test",
            "text": "New document content",
            "is_public": "on",
        }
        response = self.client.post(self.document_create_url, data)

        self.assertRedirects(response, "/dashboard/")

        # Проверяем создание документа
        doc = Document.objects.filter(text="New document content").first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.rubrics, ["python", "test"])
        self.assertTrue(doc.is_public)
        self.assertEqual(doc.text_source, "manual")

    def test_document_create_from_file(self):
        """Создание документа из файла"""
        uploaded_file = SimpleUploadedFile("test.pdf", b"PDF content", content_type="application/pdf")
        data = {
            "rubrics": "python",
            "file": uploaded_file,
        }
        response = self.client.post(self.document_create_url, data)

        self.assertRedirects(response, "/dashboard/")

        # Проверяем создание документа
        doc = Document.objects.filter(file_name="test.pdf").first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.user, self.user)
        self.assertEqual(doc.rubrics, ["python"])
        self.assertEqual(doc.file_type, "pdf")
        self.assertEqual(doc.text_source, "file")

    def test_document_create_too_many_rubrics(self):
        """Создание документа с >10 рубриками"""
        data = {
            "rubrics": ",".join([f"rubric_{i}" for i in range(11)]),
            "text": "Test",
        }
        response = self.client.post(self.document_create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Не более 10 рубрик")

        # Проверяем, что документ не создался
        self.assertEqual(Document.objects.filter(user=self.user).count(), 0)

    def test_document_create_rubric_too_long(self):
        """Создание документа с слишком длинной рубрикой"""
        data = {
            "rubrics": "a" * 101,
            "text": "Test",
        }
        response = self.client.post(self.document_create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "слишком длинная")

    def test_document_create_text_too_long(self):
        """Создание документа с слишком длинным текстом"""
        data = {
            "rubrics": "test",
            "text": "a" * 100001,
        }
        response = self.client.post(self.document_create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текст слишком длинный")

    def test_toggle_public(self):
        """Переключение публичности документа"""
        doc = Document.objects.create(user=self.user, text="Test", is_public=False)
        toggle_url = reverse("toggle_public", args=[doc.id])

        response = self.client.post(toggle_url)

        self.assertRedirects(response, self.dashboard_url)

        doc.refresh_from_db()
        self.assertTrue(doc.is_public)

        # Повторное переключение обратно
        response = self.client.post(toggle_url)
        doc.refresh_from_db()
        self.assertFalse(doc.is_public)

    def test_toggle_public_other_user_document(self):
        """Нельзя переключить публичность чужого документа"""
        other_doc = Document.objects.create(user=self.other_user, text="Other doc", is_public=False)
        toggle_url = reverse("toggle_public", args=[other_doc.id])

        response = self.client.post(toggle_url)

        self.assertEqual(response.status_code, 404)
        other_doc.refresh_from_db()
        self.assertFalse(other_doc.is_public)  # не изменилось

    def test_search_history_page(self):
        """Страница истории поиска"""
        SearchHistory.objects.create(user=self.user, query="python", results_count=5)
        SearchHistory.objects.create(user=self.user, query="django", results_count=3)

        response = self.client.get(self.search_history_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "search_history.html")
        self.assertContains(response, "python")
        self.assertContains(response, "django")
        self.assertContains(response, "5")
        self.assertContains(response, "3")

    def test_clear_history(self):
        """Очистка истории поиска"""
        SearchHistory.objects.create(user=self.user, query="python")
        SearchHistory.objects.create(user=self.user, query="django")

        response = self.client.post(self.clear_history_url)

        self.assertRedirects(response, self.search_history_url)
        self.assertEqual(SearchHistory.objects.filter(user=self.user).count(), 0)

    def test_delete_history_item(self):
        """Удаление отдельной записи истории"""
        history = SearchHistory.objects.create(user=self.user, query="python")
        delete_url = reverse("delete_history_item", args=[history.id])

        response = self.client.post(delete_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertFalse(SearchHistory.objects.filter(id=history.id).exists())

    def test_delete_history_item_other_user(self):
        """Нельзя удалить чужую запись истории"""
        other_history = SearchHistory.objects.create(user=self.other_user, query="python")
        delete_url = reverse("delete_history_item", args=[other_history.id])

        response = self.client.post(delete_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SearchHistory.objects.filter(id=other_history.id).exists())

    def test_document_detail_own_private(self):
        """Просмотр своего приватного документа"""
        doc = Document.objects.create(user=self.user, text="My private doc", is_public=False)
        detail_url = reverse("document_detail", args=[doc.id])

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "document_detail.html")
        self.assertContains(response, "My private doc")
        self.assertContains(response, "Приватный")

    def test_document_detail_other_public(self):
        """Просмотр чужого публичного документа"""
        other_public_doc = Document.objects.create(user=self.other_user, text="Other public doc", is_public=True)
        detail_url = reverse("document_detail", args=[other_public_doc.id])

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other public doc")
        self.assertContains(response, "Публичный")

    def test_document_detail_other_private(self):
        """Нельзя просмотреть чужой приватный документ"""
        other_private_doc = Document.objects.create(user=self.other_user, text="Other private doc", is_public=False)
        detail_url = reverse("document_detail", args=[other_private_doc.id])

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)

    def test_document_delete(self):
        """Удаление документа (AJAX DELETE)"""
        doc = Document.objects.create(user=self.user, text="To delete")
        delete_url = reverse("document_delete", args=[doc.id])

        response = self.client.delete(delete_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 200)  # HttpResponseClientRefresh
        self.assertFalse(Document.objects.filter(id=doc.id).exists())

    def test_document_delete_other(self):
        """Нельзя удалить чужой документ"""
        other_doc = Document.objects.create(user=self.other_user, text="Other doc")
        delete_url = reverse("document_delete", args=[other_doc.id])

        response = self.client.delete(delete_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Document.objects.filter(id=other_doc.id).exists())
