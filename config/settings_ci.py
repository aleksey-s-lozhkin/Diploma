import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

from elasticsearch_dsl import connections

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-ci-test-key-1234567890"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_htmx",
    # Приложение подключено намеренно: именно его сигналы писали в Elasticsearch
    # без обработки ошибок и роняли создание документа. Без него регрессионные
    # тесты из tests/test_resilience.py были бы вхолостую.
    "django_elasticsearch_dsl",
    "users",
    "documents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Версия статики: список здесь свой, поэтому процессор повторяем.
                "config.context.asset_version",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

AUTH_USER_MODEL = "users.User"

# Отключаем Elasticsearch полностью
ELASTICSEARCH_DSL = {"default": {"hosts": "http://localhost:9200"}}
ELASTICSEARCH_DSL_AUTO_REFRESH = False
# Должно совпадать с продакшеном: включённый автосинк библиотеки пишет в ES без
# обработки ошибок и роняет Document.save().
ELASTICSEARCH_DSL_AUTOSYNC = False

# Мокаем клиент Elasticsearch

mock_es = MagicMock()
mock_es.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

connections.add_connection("default", mock_es)

# Отключаем кэш (чтобы не было delete_pattern)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

STATIC_URL = "/static/"
MEDIA_URL = "/media/"
# Без MEDIA_ROOT загруженные в тестах файлы падали в рабочий каталог — внутрь
# пакета documents/2026/<месяц>/<день>/. Складываем их во временный каталог.
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="diploma-test-media-"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    # Должно совпадать с продакшеном: без этого drf-spectacular отказывается
    # строить схему, и её нельзя проверить в CI.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# Заголовок схемы берётся из этих настроек: без них сгенерированная в CI схема
# отличалась бы от опубликованной пустыми title и version.
SPECTACULAR_SETTINGS = {
    "TITLE": "DocSearch API",
    "DESCRIPTION": "API для поиска по документам с аутентификацией",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

CSRF_TRUSTED_ORIGINS = []
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "ERROR"},
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = "default"
