"""Устойчивость к отказам зависимостей.

Главный сценарий, ради которого эти тесты написаны: недоступный Elasticsearch
ронял создание документа, потому что библиотечные сигналы django-elasticsearch-dsl
пишут в ES без обработки ошибок, а исключение выходит прямо из Document.save().
Отказ Redis ломал запрос ещё раньше — на проверке rate limit.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from elasticsearch.exceptions import ConnectionError as ElasticsearchConnectionError
from elasticsearch_dsl.connections import connections as es_connections
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from documents.documents import DocumentIndex
from documents.models import Document
from documents.rate_limit import RateLimiters

User = get_user_model()


def _broken_elasticsearch():
    """Контекст, в котором любая запись в Elasticsearch падает."""
    client = es_connections.get_connection()
    error = ElasticsearchConnectionError("Elasticsearch недоступен")
    return mock.patch.object(client, "bulk", side_effect=error)


class ElasticsearchOutageTest(TestCase):
    """Сохранение документа не зависит от Elasticsearch."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="es-down@example.com", password="pass12345", is_active=True, is_email_verified=True
        )

    def test_document_is_created_when_elasticsearch_is_down(self):
        with _broken_elasticsearch():
            with self.captureOnCommitCallbacks(execute=True):
                document = Document.objects.create(user=self.user, rubrics=["тест"], text="проверка", is_public=False)

        self.assertIsNotNone(document.pk)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_web_form_creates_document_when_elasticsearch_is_down(self):
        client = Client()
        client.force_login(self.user)

        with _broken_elasticsearch():
            with self.captureOnCommitCallbacks(execute=True):
                response = client.post(
                    reverse("document_create"),
                    {"rubrics": "тест", "text": "текст документа"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 1)

    def test_api_creates_document_when_elasticsearch_is_down(self):
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.user)}")

        with _broken_elasticsearch():
            with self.captureOnCommitCallbacks(execute=True):
                response = api_client.post(
                    reverse("document-list"),
                    {"text": "документ через API", "rubrics": ["api"]},
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 1)

    def test_automatic_indexing_stays_disabled(self):
        """Регрессия: включённый автосинк библиотеки снова начнёт ронять save()."""
        self.assertTrue(DocumentIndex.django.ignore_signals)
        self.assertFalse(settings.ELASTICSEARCH_DSL_AUTOSYNC)


class RedisOutageTest(TestCase):
    """Недоступный кэш не превращается в ошибку запроса."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="redis-down@example.com", password="pass12345", is_active=True, is_email_verified=True
        )

    def test_rate_limiter_allows_request_when_cache_is_down(self):
        limiter = RateLimiters.api_general()
        with mock.patch("documents.rate_limit.cache.get", side_effect=ConnectionError("Redis недоступен")):
            allowed, remaining, retry_after = limiter.check("user_1_create")

        self.assertTrue(allowed)
        self.assertEqual(remaining, limiter.limit)
        self.assertEqual(retry_after, 0)

    def test_web_form_creates_document_when_cache_is_down(self):
        client = Client()
        client.force_login(self.user)

        with mock.patch("documents.rate_limit.cache.get", side_effect=ConnectionError("Redis недоступен")):
            with mock.patch("documents.rate_limit.cache.set", side_effect=ConnectionError("Redis недоступен")):
                response = client.post(
                    reverse("document_create"),
                    {"rubrics": "тест", "text": "текст документа"},
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 1)

    def test_cache_invalidation_failure_does_not_break_save(self):
        broken_cache = mock.Mock()
        broken_cache.delete_pattern.side_effect = ConnectionError("Redis недоступен")

        with mock.patch("documents.signals.cache", broken_cache):
            with self.captureOnCommitCallbacks(execute=True):
                document = Document.objects.create(user=self.user, rubrics=[], text="текст")

        self.assertTrue(Document.objects.filter(pk=document.pk).exists())


class HealthEndpointTest(TestCase):
    """Liveness не зависит от зависимостей, readiness отчитывается по ним."""

    def test_liveness_answers_without_dependencies(self):
        response = self.client.get(reverse("health_liveness"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_reports_every_dependency(self):
        response = self.client.get(reverse("health_readiness"))

        self.assertEqual(response.status_code, 200)
        checks = response.json()["checks"]
        self.assertEqual(checks["database"], "ok")
        self.assertIn("redis", checks)
        self.assertIn("elasticsearch", checks)

    def test_readiness_fails_when_database_is_unavailable(self):
        with mock.patch("config.health.connections") as broken_connections:
            broken_connections.__getitem__.return_value.cursor.side_effect = Exception("база недоступна")
            response = self.client.get(reverse("health_readiness"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
