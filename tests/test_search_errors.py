"""Отказ Elasticsearch не должен выглядеть как внутренняя ошибка.

Ловились только ConnectionError и NotFoundError: 401/403/429 от Elasticsearch
или блокировка кластера давали 500 — и в веб-интерфейсе, и в API. Веб-интерфейс
показывает понятное сообщение, API отвечает 503 (временная недоступность), а не
500 (ошибка на нашей стороне).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from elasticsearch.exceptions import TransportError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class WebSearchDegradationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="web-degrade@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_non_connection_transport_error_degrades_gracefully(self):
        with mock.patch("documents.views.views_web.SearchService") as service:
            service.return_value.search.side_effect = TransportError(429, "rejected")
            response = self.client.post(reverse("search_results"), {"query": "тест"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Поиск временно недоступен")

    def test_missing_index_is_reported_as_configuration_error(self):
        from elasticsearch.exceptions import NotFoundError

        with mock.patch("documents.views.views_web.SearchService") as service:
            service.return_value.search.side_effect = NotFoundError(404, "index_not_found_exception")
            response = self.client.post(reverse("search_results"), {"query": "тест"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ошибка конфигурации поиска")


class ApiSearchDegradationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="api-degrade@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}")

    def test_elasticsearch_failure_returns_503(self):
        with mock.patch("documents.views.views_api.SearchService") as service:
            service.return_value.search.side_effect = TransportError(503, "cluster_block_exception")
            response = self.client.post(reverse("api_search"), {"query": "тест"}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertIn("недоступен", response.data["error"])

    def test_search_still_works_on_success(self):
        with mock.patch("documents.views.views_api.SearchService") as service:
            service.return_value.search.return_value = mock.Mock(results=[], total=0, total_pages=0)
            response = self.client.post(reverse("api_search"), {"query": "тест"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
