"""Настройки, которые обязаны читаться из окружения.

CORS_ALLOWED_ORIGINS в продакшене молча подменялся захардкоженным списком
доменов, и переменная из .env не действовала: кросс-доменный клиент получал
отказ, причину которого не видно ни в логах, ни в настройках.
"""

import importlib
import os
from unittest import mock

from django.test import SimpleTestCase

from config import settings as settings_module


class CorsSettingsTest(SimpleTestCase):
    def test_allowed_origins_come_from_environment(self):
        with mock.patch.dict(
            os.environ,
            {"CORS_ALLOWED_ORIGINS": "https://consumer.example, https://second.example"},
        ):
            importlib.reload(settings_module)
            try:
                self.assertEqual(
                    settings_module.CORS_ALLOWED_ORIGINS,
                    ["https://consumer.example", "https://second.example"],
                )
            finally:
                # Возвращаем модуль в исходное состояние, чтобы не влиять на
                # остальные тесты.
                importlib.reload(settings_module)

    def test_empty_entries_are_dropped(self):
        with mock.patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://one.example,,"}):
            importlib.reload(settings_module)
            try:
                self.assertEqual(settings_module.CORS_ALLOWED_ORIGINS, ["https://one.example"])
            finally:
                importlib.reload(settings_module)
