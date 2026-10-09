"""Шаблоны не должны показывать собственные комментарии.

`{# ... #}` в Django комментирует только до конца строки: многострочный
комментарий им не закрыть, и текст такого блока уезжает на страницу обычным
текстом. Ошибка тихая — её не видно ни в тестах, ни в консоли, только глазом в
браузере, поэтому проверка обходит все страницы, а не одну.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from documents.models import Document

User = get_user_model()

#: Что ищем в готовой странице: и открытие, и закрытие комментария.
LEAKS = ("{#", "#}", "{% comment %}", "{% endcomment %}")


class NoTemplateCommentLeakTest(TestCase):
    def setUp(self):
        # Почта подтверждена: иначе страницы отвечают редиректом на проверку.
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.document = Document.objects.create(user=self.user, text="Договор поставки", rubrics=["право"])

    def assert_clean(self, response, where):
        self.assertEqual(response.status_code, 200, f"{where}: страница не открылась")
        body = response.content.decode()
        for leak in LEAKS:
            self.assertNotIn(leak, body, f"{where}: на страницу попал шаблонный комментарий {leak}")

    def test_anonymous_pages(self):
        for name in ("login", "register", "password_reset_request"):
            with self.subTest(name=name):
                self.assert_clean(self.client.get(reverse(name)), name)

    def test_authenticated_pages(self):
        self.client.force_login(self.user)
        for name in ("index", "dashboard", "document_create", "search_history"):
            with self.subTest(name=name):
                self.assert_clean(self.client.get(reverse(name)), name)

    def test_document_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("document_detail", args=[self.document.pk]))
        self.assert_clean(response, "document_detail")

    def test_change_password_page(self):
        self.client.force_login(self.user)
        self.assert_clean(self.client.get(reverse("change_password")), "change_password")

    def test_search_results_fragment(self):
        """Партиал подставляется в страницу отдельно — проверяем и его."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("search_results"), {"query": "договор"})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for leak in LEAKS:
            self.assertNotIn(leak, body, f"search_results: на страницу попал {leak}")
