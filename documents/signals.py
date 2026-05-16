from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .documents import DocumentIndex
from .models import Document


@receiver(post_save, sender=Document)
def index_document(sender, instance, **kwargs):
    """Автоматическая индексация при сохранении документа"""
    try:
        DocumentIndex().update(instance)
        print(f"Document {instance.id} indexed successfully")
    except Exception as e:
        print(f"Error indexing document {instance.id}: {e}")


@receiver(post_delete, sender=Document)
def delete_document(sender, instance, **kwargs):
    """Автоматическое удаление из индекса при удалении документа"""
    try:
        DocumentIndex().delete(instance)
        print(f"Document {instance.id} deleted from index")
    except Exception as e:
        print(f"Error deleting document {instance.id} from index: {e}")
