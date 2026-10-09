"""Переизвлечение текста из уже загруженных файлов.

Нужно после смены экстрактора: у документов в базе лежит текст, извлечённый
прежним способом, и он хуже. Команда читает файлы заново, обновляет текст и
переиндексирует документы — иначе улучшение коснётся только новых загрузок.
"""

from django.core.management.base import BaseCommand

from documents.models import Document
from documents.utils import extract_text_from_file


class Command(BaseCommand):
    help = "Перечитать файлы документов и обновить извлечённый текст"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Показать, что изменится, и не сохранять")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changed = skipped = 0

        for document in Document.objects.exclude(file="").exclude(file=None).iterator():
            try:
                with document.file.open("rb") as handle:
                    fresh = extract_text_from_file(handle, document.file_type)
            except Exception as exc:  # noqa: BLE001 — один битый файл не должен ронять проход
                self.stderr.write(f"#{document.pk}: не удалось прочитать файл: {exc}")
                skipped += 1
                continue

            if len(fresh) <= len(document.text or ""):
                skipped += 1
                continue

            self.stdout.write(f"#{document.pk} {document.file_name}: {len(document.text or '')} → {len(fresh)} знаков")
            changed += 1
            if not dry_run:
                document.text = fresh
                # save() запускает переиндексацию в Elasticsearch (best-effort).
                document.save(update_fields=["text"])

        suffix = " (пробный проход, не сохранено)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"Обновлено: {changed}, без изменений: {skipped}{suffix}"))
