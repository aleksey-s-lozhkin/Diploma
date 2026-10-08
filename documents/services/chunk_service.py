"""Куски документов в отдельном индексе Elasticsearch.

Зачем отдельный индекс, а не поле в `documents`: один документ даёт десятки
кусков, и хранить их в том же документе значит потерять постраничность и
усложнить удаление. Индекс `documents` остаётся как есть — полнотекстовый поиск
по целым документам продолжает работать.

Сборка кусков — чистая функция (`build_chunk_payloads`): её можно проверить без
Elasticsearch, а запись в индекс остаётся тонкой обёрткой. Ошибки записи наружу
не уходят: поиск — ускоритель, а не источник правды, и падение индексации не
должно ломать загрузку документа.
"""

import hashlib
import logging

from elasticsearch.helpers import bulk
from elasticsearch_dsl.connections import connections

from documents.chunking import split_into_chunks
from documents.models import Document

logger = logging.getLogger(__name__)

#: Имя индекса кусков. Закреплено за этим проектом, как и `documents`.
CHUNKS_INDEX = "chunks"


def document_title(document) -> str:
    """Заголовок для человека: имя файла, рубрика или номер.

    В контракте (docs/SEARCH-CONTRACT.md, §3) заголовок нужен потому, что
    человеку показывают «откуда это», а не идентификатор.
    """
    if document.file_name:
        return document.file_name
    if document.rubrics:
        return document.rubrics[0]
    return f"Документ #{document.pk}"


def document_version(document) -> str:
    """Отпечаток содержимого документа.

    Ответ на вопрос §8.3 контракта: потребитель должен уметь понять, что
    отрывок устарел. Хеш считается от текста, поэтому переиндексация документа
    даёт новое значение, а неизменённый документ — то же самое, и потребителю не
    нужно перезапрашивать всё подряд.
    """
    return hashlib.sha256((document.text or "").encode("utf-8")).hexdigest()[:12]


def build_chunk_payloads(document) -> list:
    """Собрать куски документа для индекса. Без обращений к Elasticsearch."""
    chunks = split_into_chunks(document.text or "")
    total = len(chunks)
    title = document_title(document)
    version = document_version(document)
    rubrics = document.rubrics or []

    return [
        {
            # Идентификатор в индексе — пара «документ:кусок»: переиндексация
            # перезаписывает те же записи, а не плодит дубликаты.
            "_id": f"{document.pk}:{chunk.index}",
            "document_id": document.pk,
            "chunk_index": chunk.index,
            "chunk_total": total,
            "document_version": version,
            "title": title,
            "text": chunk.text,
            "rubrics": rubrics,
            "is_public": document.is_public,
            "user_id": document.user_id,
        }
        for chunk in chunks
    ]


def index_document_chunks(document_id) -> int:
    """Переписать куски документа в индексе. Возвращает число записанных кусков."""
    try:
        document = Document.objects.filter(pk=document_id).first()
        if document is None:
            return 0

        payloads = build_chunk_payloads(document)
        client = connections.get_connection()
        _delete_chunks(client, document_id)

        if not payloads:
            logger.info("Документ %s пуст — кусков нет", document_id)
            return 0

        actions = [{**payload, "_index": CHUNKS_INDEX, "_op_type": "index"} for payload in payloads]
        bulk(client, actions, refresh=False)
        logger.info("Документ %s: записано кусков %s", document_id, len(payloads))
        return len(payloads)
    except Exception:
        logger.error("Не удалось проиндексировать куски документа %s", document_id, exc_info=True)
        return 0


def delete_document_chunks(document_id) -> None:
    """Убрать куски документа из индекса."""
    try:
        _delete_chunks(connections.get_connection(), document_id)
        logger.info("Документ %s: куски удалены из индекса", document_id)
    except Exception:
        logger.error("Не удалось удалить куски документа %s", document_id, exc_info=True)


def _delete_chunks(client, document_id) -> None:
    client.delete_by_query(
        index=CHUNKS_INDEX,
        body={"query": {"term": {"document_id": document_id}}},
        # Индекса может ещё не быть — это не ошибка удаления.
        ignore=[404],
        conflicts="proceed",
    )
