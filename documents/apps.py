from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Конфигурация приложения Documents"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "Документы"

    def ready(self):
        """Импортируем сигналы при готовности приложения"""
        from . import signals  # noqa: F401
