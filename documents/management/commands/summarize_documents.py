"""Описания документов через языковую модель.

Отдельная команда нужна и для уже загруженных документов, и для повторного
прохода после смены модели.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from documents.models import Document
from documents.services.summary_service import is_enabled, summarize_document


class Command(BaseCommand):
    help = "Получить краткое описание и теги документов от языковой модели"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Обновить и те, у кого описание уже есть")
        parser.add_argument("--limit", type=int, default=0, help="Сколько документов обработать (0 — все)")
        parser.add_argument("--dry-run", action="store_true", help="Показать, что будет обработано")

    def handle(self, *args, **options):
        if not is_enabled():
            self.stderr.write("Модель не настроена: пусто OLLAMA_URL")
            return

        queryset = Document.objects.order_by("id")
        if not options["all"]:
            queryset = queryset.filter(summary="")
        if options["limit"]:
            queryset = queryset[: options["limit"]]

        total = queryset.count()
        self.stdout.write(f"Модель {getattr(settings, 'OLLAMA_MODEL', 'qwen3:8b')}, документов к обработке: {total}")
        if options["dry_run"]:
            for document in queryset:
                self.stdout.write(f"  #{document.pk} {document.file_name or 'текст'} ({len(document.text)} знаков)")
            return

        done = failed = 0
        for document in queryset:
            if summarize_document(document):
                document.refresh_from_db()
                done += 1
                self.stdout.write(f"#{document.pk} {document.file_name or 'текст'}: {document.summary[:90]}")
                self.stdout.write(f"   теги: {' '.join('#' + tag for tag in document.keywords)}")
            else:
                failed += 1
                self.stdout.write(f"#{document.pk}: описание не получено")

        self.stdout.write(self.style.SUCCESS(f"Готово: с описанием {done}, без {failed}"))
