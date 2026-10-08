"""Дымовые тесты админки.

Админка не покрывалась вообще: ошибка в list_display, list_filter или fieldsets
проявляется только при открытии страницы, то есть у пользователя. Отдельно
проверяется фильтр по JSONField: rubrics — это JSONField, и такой фильтр в
некоторых версиях Django роняет список документов.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from documents.models import Document, SearchHistory

User = get_user_model()


class AdminSmokeTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@example.com", password="adminpass123")
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.document = Document.objects.create(
            user=self.user,
            rubrics=["python", "django"],
            text="Текст документа для админки",
            is_public=True,
            text_source="manual",
        )
        self.history = SearchHistory.objects.create(user=self.user, query="python", results_count=1)
        self.client.force_login(self.admin)

    def test_admin_index_loads(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

    def test_document_changelist_with_json_rubrics(self):
        """Список документов и фильтр по рубрикам в JSONField"""
        response = self.client.get(reverse("admin:documents_document_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текст документа")

    def test_document_add_and_change_pages(self):
        add_response = self.client.get(reverse("admin:documents_document_add"))
        self.assertEqual(add_response.status_code, 200)

        change_response = self.client.get(reverse("admin:documents_document_change", args=[self.document.pk]))
        self.assertEqual(change_response.status_code, 200)

    def test_search_history_changelist_loads(self):
        response = self.client.get(reverse("admin:documents_searchhistory_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_user_changelist_and_change_pages(self):
        changelist = self.client.get(reverse("admin:users_user_changelist"))
        self.assertEqual(changelist.status_code, 200)

        change = self.client.get(reverse("admin:users_user_change", args=[self.user.pk]))
        self.assertEqual(change.status_code, 200)
