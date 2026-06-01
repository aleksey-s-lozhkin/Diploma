import os

from .settings import INSTALLED_APPS  # noqa: F401

os.environ["ELASTICSEARCH_DSL_AUTO_REFRESH"] = "False"
os.environ["ELASTICSEARCH_DSL_SIGNALS"] = "False"

# Используем SQLite для CI тестов
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Отключаем кэширование
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Отключаем Elasticsearch
ELASTICSEARCH_DSL = {
    "default": {"hosts": "http://localhost:9200"},
}
ELASTICSEARCH_DSL_AUTO_REFRESH = False

# Удаляем django_elasticsearch_dsl из INSTALLED_APPS
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "django_elasticsearch_dsl"]

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
        "level": "ERROR",
    },
}
