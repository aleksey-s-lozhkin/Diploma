"""Проверки состояния приложения для healthcheck и деплоя.

Два разных вопроса — два эндпоинта:

``/health/``
    liveness: процесс жив и отвечает. Зависимости не опрашиваются, иначе
    перезапуск контейнера запускался бы из-за чужого сбоя.

``/health/ready/``
    readiness: приложение способно обслуживать запросы. Обязательна только
    база данных. Redis и Elasticsearch проверяются и попадают в отчёт, но их
    отказ не делает приложение неготовым: кэш и поиск деградируют, а загрузка
    и чтение документов продолжают работать.
"""

import logging

from django.db import connections
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def liveness(request):
    """Процесс отвечает."""
    return JsonResponse({"status": "ok"})


def readiness(request):
    """Готовность обслуживать запросы с отчётом по зависимостям."""
    checks = {}
    ready = True

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — в отчёт попадает любая причина
        logger.error("Проверка базы данных не прошла: %s", exc, exc_info=True)
        checks["database"] = f"error: {exc}"
        ready = False

    checks["redis"] = _check_redis()
    checks["elasticsearch"] = _check_elasticsearch()

    return JsonResponse(
        {
            "status": "ok" if ready else "unavailable",
            "checks": checks,
        },
        status=200 if ready else 503,
    )


def _check_redis():
    """Отдаёт ok/degraded. При IGNORE_EXCEPTIONS кэш молча возвращает None."""
    try:
        from django.core.cache import cache

        cache.set("health:probe", "1", timeout=5)
        if cache.get("health:probe") == "1":
            return "ok"
        return "degraded: значение не сохранилось"
    except Exception as exc:  # noqa: BLE001
        return f"degraded: {exc}"


def _check_elasticsearch():
    """Отдаёт ok/degraded. Поиск не критичен для сохранения документов."""
    try:
        from elasticsearch_dsl.connections import connections as es_connections

        es_connections.get_connection().info()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"degraded: {exc}"
