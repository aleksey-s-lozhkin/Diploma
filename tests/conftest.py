"""Общие фикстуры тестов.

``config.settings_ci`` подменяет соединение с Elasticsearch на MagicMock, но
конфигурация приложения ``django_elasticsearch_dsl`` при загрузке пересоздаёт
соединение по настройкам ``ELASTICSEARCH_DSL``. Мок возвращается на место,
иначе тесты пошли бы в настоящий HTTP на localhost:9200.
"""

import pytest
from elasticsearch_dsl import connections

from config import settings_ci


@pytest.fixture(autouse=True, scope="session")
def elasticsearch_mock_connection():
    """Возвращает мок-соединение Elasticsearch после инициализации приложений."""
    connections.add_connection("default", settings_ci.mock_es)
    yield
