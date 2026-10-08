"""Проверки исправленных дефектов создания, поиска и удаления документов."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from elasticsearch_dsl import Search

from documents.constants import MAX_FILE_SIZE
from documents.models import Document
from documents.services.search_service import SearchService

User = get_user_model()


class FakeEsResponse:
    """Минимальный ответ Elasticsearch: hits.total.value и пустой список hits."""

    class hits:
        class total:
            value = 0

    def __iter__(self):
        return iter([])


class BrokenPaginationTest(TestCase):
    """Мусор в параметре page не должен ронять страницу.

    `?page=` приходит от ботов и от пагинации с пустым значением; int("") давал
    ValueError и ответ 500.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="paging@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client = Client()
        self.client.force_login(self.user)
        Document.objects.create(user=self.user, rubrics=["тест"], text="документ")

    def test_dashboard_survives_broken_page(self):
        for value in ["", "abc", "-5", "0", "1e3"]:
            response = self.client.get(reverse("dashboard"), {"page": value})
            self.assertEqual(response.status_code, 200, f"page={value!r}")

    def test_search_history_survives_broken_page(self):
        response = self.client.get(reverse("search_history"), {"page": ""})
        self.assertEqual(response.status_code, 200)

    def test_search_results_survive_broken_page(self):
        with mock.patch("documents.views.views_web.SearchService") as service:
            service.return_value.search.return_value = mock.Mock(results=[], total=0, total_pages=0)
            response = self.client.post(reverse("search_results"), {"query": "тест", "page": ""})

        self.assertEqual(response.status_code, 200)


class UploadValidationTest(TestCase):
    """Web-форма проверяет файл так же, как API."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="upload@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_unsupported_type_is_rejected(self):
        uploaded = SimpleUploadedFile("virus.exe", b"MZ...", content_type="application/octet-stream")

        response = self.client.post(reverse("document_create"), {"rubrics": "тест", "file": uploaded})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неподдерживаемый тип файла")
        self.assertEqual(Document.objects.count(), 0)

    def test_too_large_file_is_rejected(self):
        uploaded = SimpleUploadedFile("big.txt", b"a" * (MAX_FILE_SIZE + 1), content_type="text/plain")

        with mock.patch("documents.constants.MAX_FILE_SIZE", 1024 * 1024):
            response = self.client.post(reverse("document_create"), {"rubrics": "тест", "file": uploaded})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Файл больше")
        self.assertEqual(Document.objects.count(), 0)

    def test_text_file_is_extracted_and_stored(self):
        uploaded = SimpleUploadedFile("notes.txt", "привет мир".encode(), content_type="text/plain")

        response = self.client.post(reverse("document_create"), {"rubrics": "тест", "file": uploaded})

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get()
        self.assertEqual(document.text, "привет мир")
        self.assertEqual(document.file_type, "txt")
        self.assertEqual(document.text_source, "file")
        # Файл сохранён с содержимым: раньше он записывался до чтения, и повторная
        # запись из MEDIA_ROOT могла дать пустой файл.
        with document.file.open("rb") as stored:
            self.assertEqual(stored.read(), "привет мир".encode())


class DocumentFileCleanupTest(TestCase):
    """Удаление документа убирает и его файл."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cleanup@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_delete_removes_file_from_storage(self):
        uploaded = SimpleUploadedFile("to-delete.txt", b"content", content_type="text/plain")
        self.client.post(reverse("document_create"), {"rubrics": "тест", "file": uploaded})
        document = Document.objects.get()
        storage, name = document.file.storage, document.file.name
        self.assertTrue(storage.exists(name))

        response = self.client.delete(reverse("document_delete", args=[document.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(storage.exists(name))
        self.assertEqual(Document.objects.count(), 0)


class SearchSortingTest(TestCase):
    """Сортировка выполняется Elasticsearch, а не списком текущей страницы."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sort@example.com", password="pass12345", is_active=True, is_email_verified=True
        )

    def _capture_sort(self, sort):
        captured = {}

        def fake_execute(search_self):
            captured["body"] = search_self.to_dict()
            return FakeEsResponse()

        with mock.patch.object(Search, "execute", new=fake_execute):
            SearchService(self.user).search(query="тест", page=1, save_history=False, with_highlights=False, sort=sort)
        return captured["body"].get("sort")

    def test_date_sort_is_sent_to_elasticsearch(self):
        self.assertEqual(self._capture_sort("date"), [{"created_date": {"order": "desc"}}])

    def test_date_asc_sort_is_sent_to_elasticsearch(self):
        # По возрастанию elasticsearch_dsl отдаёт компактную форму без order.
        self.assertEqual(self._capture_sort("date_asc"), ["created_date"])

    def test_relevance_sort_uses_score(self):
        self.assertEqual(self._capture_sort("relevance"), ["_score"])
