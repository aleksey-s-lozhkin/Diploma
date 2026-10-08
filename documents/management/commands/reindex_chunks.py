"""Пересборка индекса кусков из базы.

Индекс кусков производный: он собирается из текста документов, поэтому его
всегда можно пересоздать. Команда нужна после первого деплоя и после смены
правил нарезки — в автоматический запуск контейнера она не вынесена, чтобы
недоступный Elasticsearch не мешал приложению подняться.
"""

from django.core.management.base import BaseCommand
from elasticsearch_dsl.connections import connections

from documents.documents import chunks_index
from documents.models import Document
from documents.services.chunk_service import CHUNKS_INDEX, index_document_chunks


class Command(BaseCommand):
    help = "Пересобрать индекс кусков (chunks) из документов в базе"

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=200, help="Сколько документов обрабатывать за проход")

    def handle(self, *args, **options):
        client = connections.get_connection()

        if chunks_index.exists():
            self.stdout.write("Индекс кусков уже есть — удаляю и создаю заново.")
            chunks_index.delete(ignore=[404])
        chunks_index.create()

        total_chunks = 0
        total_documents = 0
        queryset = Document.objects.only("id").order_by("id").iterator(chunk_size=options["batch"])
        for document in queryset:
            total_chunks += index_document_chunks(document.pk)
            total_documents += 1

        # Один refresh в конце: обновлять индекс на каждом документе незачем.
        client.indices.refresh(index=CHUNKS_INDEX)

        health = client.cat.indices(index=CHUNKS_INDEX, format="json", h="index,health,docs.count")
        self.stdout.write(
            self.style.SUCCESS(
                f"Обработано документов: {total_documents}, записано кусков: {total_chunks}. " f"Индекс: {health}"
            )
        )
