from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.services.search_service import SearchService

User = get_user_model()


class SearchServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        self.service = SearchService(self.user)

    def test_search_empty_query(self):
        """Пустой поисковый запрос"""
        response = self.service.search(query="")
        self.assertEqual(response.total, 0)
        self.assertEqual(response.results, [])

    def test_build_query_with_rubric(self):
        """Построение запроса с рубрикой"""
        query = self.service.build_query(query="python", rubric="django")
        self.assertIsNotNone(query)

    def test_build_query_with_privacy_public(self):
        """Построение запроса с privacy=public"""
        query = self.service.build_query(query="python", privacy="public")
        self.assertIsNotNone(query)

    def test_build_query_with_privacy_private(self):
        """Построение запроса с privacy=private"""
        query = self.service.build_query(query="python", privacy="private")
        self.assertIsNotNone(query)

    def test_format_text_truncation(self):
        """Обрезание длинного текста"""
        long_text = "a" * 600
        truncated = self.service.format_text(long_text, max_length=500)
        self.assertEqual(len(truncated), 503)
        self.assertTrue(truncated.endswith("..."))
