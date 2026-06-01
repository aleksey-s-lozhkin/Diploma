from django_elasticsearch_dsl.signals import post_delete, post_save

from .settings import *  # noqa: F403, F401

# Используем SQLite для CI тестов
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ELASTICSEARCH_DSL = {
    "default": {"hosts": "http://localhost:9200"},
}
ELASTICSEARCH_DSL_AUTO_REFRESH = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

post_save.disconnect(dispatch_uid="elasticsearch_dsl.signals.handle_save")
post_delete.disconnect(dispatch_uid="elasticsearch_dsl.signals.handle_delete")

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
