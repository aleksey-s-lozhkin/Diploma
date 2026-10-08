"""Синхронизация документов с Elasticsearch и сброс кэша рубрик.

Индексация — вспомогательная операция: отказ Elasticsearch не должен
превращаться в ошибку сохранения документа. Поэтому каждый шаг здесь обёрнут в
try/except, а работа отложена до коммита транзакции: индексировать то, что ещё
может откатиться, бессмысленно.

Автоматические сигналы django-elasticsearch-dsl отключены (см.
documents/documents.py), иначе библиотека пишет в ES параллельно и без
обработки ошибок.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .documents import DocumentIndex
from .models import Document
from .rubrics import invalidate_rubrics_cache
from .services.chunk_service import delete_document_chunks, index_document_chunks

logger = logging.getLogger(__name__)


def _index_document(document_id):
    """Кладёт документ в индекс. Ошибка ES остаётся в логе."""
    try:
        instance = Document.objects.filter(pk=document_id).first()
        if instance is None:
            return
        DocumentIndex().update(instance, refresh=False)
        logger.info("Документ %s проиндексирован", document_id)
    except Exception:
        logger.error("Не удалось проиндексировать документ %s", document_id, exc_info=True)


def _delete_from_index(document_id):
    """Убирает документ из индекса по идентификатору.

    У django-elasticsearch-dsl нет удаления по объекту модели: унаследованный
    DocType.delete() работает с meta.id документа индекса, которого у свежего
    экземпляра нет. Прежний вызов DocumentIndex().delete(instance) из-за этого
    всегда падал, и удалённые документы продолжали находиться поиском.
    """
    try:
        DocumentIndex()._get_connection().delete(
            index=DocumentIndex._index._name,
            id=document_id,
            ignore=[404],
        )
        logger.info("Документ %s удалён из индекса", document_id)
    except Exception:
        logger.error("Не удалось удалить документ %s из индекса", document_id, exc_info=True)


@receiver(post_save, sender=Document)
def index_document(sender, instance, **kwargs):
    """Индексирует документ после коммита и сбрасывает кэш рубрик владельца."""
    document_id = instance.pk
    user_id = instance.user_id
    # Куски переиндексируются вместе с документом: изменился текст — изменились
    # и отрывки, по которым ищут потребители (docs/SEARCH-CONTRACT.md).
    transaction.on_commit(
        lambda: (
            _index_document(document_id),
            index_document_chunks(document_id),
            invalidate_rubrics_cache(user_id),
        )
    )


@receiver(post_delete, sender=Document)
def delete_document(sender, instance, **kwargs):
    """Убирает документ из индекса и сбрасывает кэш рубрик владельца.

    Идентификаторы запоминаются здесь: Django обнуляет pk сразу после отправки
    post_delete, поэтому в отложенном вызове instance.pk уже None.
    """
    document_id = instance.pk
    user_id = instance.user_id
    transaction.on_commit(
        lambda: (
            _delete_from_index(document_id),
            delete_document_chunks(document_id),
            invalidate_rubrics_cache(user_id),
        )
    )
