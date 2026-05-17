from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .documents import DocumentIndex
from .models import Document


def invalidate_user_cache(user_id):
    """Очищает кэш для конкретного пользователя (для cache_page)"""
    # Удаляем кэш дашборда (формат ключей Django)
    cache.delete(f"views.decorators.cache.cache_header.dashboard_{user_id}")
    cache.delete(f"views.decorators.cache.cache_page.dashboard_{user_id}")

    # Удаляем кэш главной страницы (общий для всех)
    cache.delete("views.decorators.cache.cache_header.index")
    cache.delete("views.decorators.cache.cache_page.index")


@receiver(post_save, sender=Document)
def index_document(sender, instance, **kwargs):
    """Автоматическая индексация при сохранении документа + очистка кэша"""
    try:
        DocumentIndex().update(instance)
        print(f"Document {instance.id} indexed successfully")
        invalidate_user_cache(instance.user.id)
    except Exception as e:
        print(f"Error indexing document {instance.id}: {e}")


@receiver(post_delete, sender=Document)
def delete_document(sender, instance, **kwargs):
    """Автоматическое удаление из индекса при удалении документа + очистка кэша"""
    try:
        DocumentIndex().delete(instance)
        print(f"Document {instance.id} deleted from index")
        invalidate_user_cache(instance.user.id)
    except Exception as e:
        print(f"Error deleting document {instance.id} from index: {e}")
