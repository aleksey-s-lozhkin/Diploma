from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from elasticsearch_dsl.connections import connections

from documents.documents import DocumentIndex
from documents.models import Document

User = get_user_model()


class Command(BaseCommand):
    """Команда для переиндексации документов в Elasticsearch"""

    help = "Reindex documents to Elasticsearch"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing index before reindexing",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Reindex only documents of specific user",
        )
        parser.add_argument(
            "--doc-id",
            type=int,
            help="Reindex only specific document by ID",
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 50)
        self.stdout.write("Starting reindexation process...")
        self.stdout.write("=" * 50)

        # Проверка подключения к Elasticsearch
        try:
            es = connections.get_connection()
            es.info()
            self.stdout.write(self.style.SUCCESS("✓ Connected to Elasticsearch"))
        except Exception as e:
            raise CommandError(f"✗ Cannot connect to Elasticsearch: {e}")

        doc_index = DocumentIndex()

        # Принудительная переиндексация (удаление существующего индекса)
        if options["force"]:
            self.stdout.write("Force mode enabled: deleting existing index...")
            try:
                doc_index._index.delete(ignore=404)
                self.stdout.write("✓ Index deleted")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠ Warning: {e}"))

        # Определяем набор документов для индексации
        if options["doc_id"]:
            # Индексация одного документа по ID
            documents = Document.objects.filter(id=options["doc_id"])
            if not documents.exists():
                raise CommandError(f"Document with id={options['doc_id']} not found")
            self.stdout.write(f"Reindexing single document (id={options['doc_id']})...")
        elif options["user_id"]:
            # Индексация документов конкретного пользователя
            documents = Document.objects.filter(user_id=options["user_id"])
            if not documents.exists():
                raise CommandError(f"No documents found for user_id={options['user_id']}")
            self.stdout.write(f"Reindexing {documents.count()} documents for user_id={options['user_id']}...")
        else:
            # Полная переиндексация всех документов
            documents = Document.objects.all()
            self.stdout.write(f"Reindexing all {documents.count()} documents...")

        # Процесс переиндексации
        success_count = 0
        error_count = 0

        for i, doc in enumerate(documents.iterator(), 1):
            try:
                doc_index.update(doc)
                success_count += 1

                # Отображение прогресса каждые 100 документов
                if i % 100 == 0:
                    self.stdout.write(f"  Progress: {i}/{documents.count()} documents indexed")

            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f"  ✗ Error indexing document {doc.id}: {e}"))

        self.stdout.write("=" * 50)
        self.stdout.write(self.style.SUCCESS(f"✓ Success: {success_count} documents indexed"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"✗ Errors: {error_count} documents failed"))
        self.stdout.write("=" * 50)
        self.stdout.write(self.style.SUCCESS("Reindexation completed!"))
