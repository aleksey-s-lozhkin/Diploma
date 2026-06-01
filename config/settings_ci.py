from .settings import *  # noqa: F403, F401

# Используем SQLite для CI тестов
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Отключаем Elasticsearch для тестов
ELASTICSEARCH_DSL = {
    "default": {"hosts": "http://localhost:9200"},
}
ELASTICSEARCH_DSL_AUTO_REFRESH = False

# Отключаем кэширование для тестов
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

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
        "level": "INFO",
    },
}
