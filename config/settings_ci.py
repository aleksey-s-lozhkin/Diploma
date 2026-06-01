from unittest.mock import MagicMock

from elasticsearch_dsl import connections

from .settings import *  # noqa: F403, F401

# Используем SQLite для CI тестов
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Отключаем кэширование для тестов
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Полностью отключаем Elasticsearch через подмену соединения

# Создаём мок для Elasticsearch клиента
mock_es = MagicMock()
mock_es.info.return_value = {"version": {"number": "8.0.0"}}
mock_es.bulk.return_value = (True, [])

# Подменяем реальный клиент на мок
connections.add_connection("default", mock_es)

# Отключаем авто-обновление
ELASTICSEARCH_DSL_AUTO_REFRESH = False

# Логи в консоль
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "ERROR",  # Уменьшаем шум в логах
    },
}
