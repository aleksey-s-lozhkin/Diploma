import logging

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .documents import DocumentIndex
from .models import Document

logger = logging.getLogger(__name__)


def invalidate_user_cache(user_id):
    """Очищает кэш для конкретного пользователя"""
    # Удаляем кэш рубрик
    cache.delete(f"rubrics_user_{user_id}")
    # Удаляем кэш статистики дашборда
    cache.delete(f"dashboard_stats_user_{user_id}")
    # Удаляем кэш количества документов
    cache.delete(f"user_docs_count_{user_id}")
    # Удаляем кэш главной страницы (кэшируется через vary_on_cookie)
    cache.delete("views.decorators.cache.cache_page.index.")
    cache.delete("views.decorators.cache.cache_header.index.")
    # Удаляем кэш страницы с пагинацией (если есть)
    cache.delete_pattern("*rubrics*")
    cache.delete_pattern(f"*dashboard*user_{user_id}*")


@receiver(post_save, sender=Document)
def index_document(sender, instance, **kwargs):
    """Автоматическая индексация при сохранении документа + очистка кэша"""
    try:
        DocumentIndex().update(instance, refresh=False)
        logger.info(f"Document {instance.id} indexed successfully")
        invalidate_user_cache(instance.user.id)
    except Exception as e:
        logger.error(f"Error indexing document {instance.id}: {e}", exc_info=True)


@receiver(post_delete, sender=Document)
def delete_document(sender, instance, **kwargs):
    """Автоматическое удаление из индекса при удалении документа"""
    try:
        # Используем refresh=False для асинхронности, ignore=404 чтобы не падать
        DocumentIndex().delete(instance)
        logger.info(f"Document {instance.id} deleted from index")
        invalidate_user_cache(instance.user.id)
    except Exception as e:
        logger.error(f"Error deleting document {instance.id} from index: {e}", exc_info=True)


@receiver(post_save, sender=Document)
def clear_cache_on_public_change(sender, instance, **kwargs):
    """Очищает кэш при изменении статуса публичности документа"""
    try:
        if hasattr(instance, "_original_is_public"):
            if instance._original_is_public != instance.is_public:
                invalidate_user_cache(instance.user.id)
    except AttributeError:
        pass  # Это нормально, просто нет атрибута
    except Exception as e:
        logger.warning(f"Error in clear_cache_on_public_change for doc {instance.id}: {e}")
