"""Описание документов, из которых не извлекается текст.

Зачем это вообще. Шпаргалка «Списки» лежит в индексе, но найти её нельзя:
весь её текст — 41 знак. Причина не в поломке, а в самом файле: **при
печати шрифты перевели в кривые**, поэтому в PDF 767 контуров и **ноль
символов**. `pdfplumber` извлекает символы, а их там нет.

Что делает команда. Показывает страницы модели, которая **видит**, и просит
у неё **только заголовки разделов**. Не текст, не код, не значения.

Почему только заголовки — это главное решение здесь, и оно из замера.
На той же странице модель прочитала заголовки **верно**:

    Списки / Создать список / Распечатать список /
    Как нумеруются элементы / Получить элемент по индексу

и **выдумала все значения**:

    numbers = [0, 1, 2, 3, 4, 5]  →  [... 6, 7, 8, 9]
    pos = 3                        →  rows = 0
    'Генрих', 'Людовик'            →  "Скрим", "Лодовик"

Заголовок, названный неточно, никого не научит неправильному. **Строка
кода — научит.** Поэтому кода в описании не будет вообще.

Что записывается. В `text` документа попадает **честная заметка**: о чём
документ (по разделам) и **прямо сказано, что основного текста нет и
почему**. Читающий поиск не должен думать, что это отрывок документа.

Запуск:

    python manage.py describe_unreadable_documents            # посмотреть, что нашлось
    python manage.py describe_unreadable_documents --apply    # записать
    python manage.py describe_unreadable_documents --apply --document 9

**Про модель.** По умолчанию `gemma3:4b` — зрительная, она уже на хосте.
Она **вытесняет общую `qwen3:8b`** на время работы (3,34 + 6,19 > 8 ГБ).
Это разовая задача, поэтому терпимо, но знать об этом надо: пока команда
работает, лапоть и Самогон ждут загрузки своей модели.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from documents.models import Document

#: Ниже этого порога считаем, что текста в документе нет.
MIN_USEFUL_TEXT = 200

#: Сколько страниц показывать модели. Больше не нужно: разделы видно и на
#: нескольких, а время растёт линейно.
MAX_PAGES = 8

#: Разрешение отрисовки. 110 dpi хватает, чтобы заголовки читались, и не
#: раздувает картинку: страница уходит в модель как есть.
RENDER_DPI = 110

PROMPT = """Это страница учебной шпаргалки по программированию.

Перечисли ТОЛЬКО заголовки разделов этой страницы, по порядку, как они напечатаны.

Строгие правила:
- НЕ приводи код, значения, примеры и результаты — ни одной строки;
- если заголовок неразборчив, напиши ровно [неразборчиво] вместо догадки;
- ничего не добавляй от себя.

Ответ — списком, каждый заголовок с новой строки, без нумерации."""


class Command(BaseCommand):
    help = "Описать документы, из которых не извлекается текст (шрифты в кривых, сканы)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="записать описание (без флага — только показать)")
        parser.add_argument("--document", type=int, default=None, help="только этот документ по id")

    def handle(self, *args, **options):
        model = getattr(settings, "OLLAMA_VISION_MODEL", "gemma3:4b")
        base_url = (getattr(settings, "OLLAMA_URL", "") or "").rstrip("/")
        if not base_url:
            raise CommandError("OLLAMA_URL не задан — описывать нечем")

        documents = Document.objects.all()
        if options["document"]:
            documents = documents.filter(id=options["document"])

        found = [d for d in documents if len((d.text or "").strip()) < MIN_USEFUL_TEXT]
        if not found:
            self.stdout.write("Документов без текста нет.")
            return

        self.stdout.write(f"Документов без текста: {len(found)}. Модель: {model}\n")

        for document in found:
            self.stdout.write(f"  #{document.id} {document.file_name} — текста {len(document.text or '')} знаков")
            sections = self._sections(document, model, base_url)
            if not sections:
                self.stdout.write("    разделы получить не удалось, пропускаю\n")
                continue

            for section in sections:
                self.stdout.write(f"      · {section}")

            note = self._note(document, sections)
            if options["apply"]:
                document.text = note
                document.save(update_fields=["text"])
                self.stdout.write("    записано в text\n")
            else:
                self.stdout.write(f"    (не записано; было бы {len(note)} знаков)\n")

        if not options["apply"]:
            self.stdout.write("\nЭто был показ. Повторить с --apply, чтобы записать.")

    @staticmethod
    def _note(document: Document, sections: list[str]) -> str:
        """Честная заметка вместо текста.

        Прямо говорит, что основного текста нет и почему. Молчаливая
        подмена описанием хуже: читающий решит, что это отрывок документа.
        """
        listing = "\n".join(f"- {section}" for section in sections)
        return (
            f"{document.file_name}\n\n"
            "Шпаргалка по программированию на Python.\n\n"
            f"Разделы:\n{listing}\n\n"
            "ВНИМАНИЕ: основной текст документа не извлечён — при печати шрифты "
            "переведены в кривые, поэтому символов в файле нет. Здесь перечислены "
            "только названия разделов, полученные по изображению страниц. "
            "Кода и примеров в этом описании нет намеренно: распознавание "
            "уверенно искажает значения, а неверная строка кода хуже её отсутствия."
        )

    def _sections(self, document: Document, model: str, base_url: str) -> list[str]:
        """Заголовки разделов по изображениям страниц."""
        try:
            import pdfplumber
        except ImportError as exc:  # pragma: no cover
            raise CommandError(f"pdfplumber не установлен: {exc}") from exc

        try:
            pdf_path = document.file.path
        except (ValueError, AttributeError):
            self.stderr.write("    у документа нет файла на диске")
            return []

        found: list[str] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:MAX_PAGES]:
                    buffer = io.BytesIO()
                    page.to_image(resolution=RENDER_DPI).save(buffer, format="PNG")
                    image = base64.b64encode(buffer.getvalue()).decode()
                    for line in self._ask(model, base_url, image):
                        if line not in found:
                            found.append(line)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"    ошибка чтения PDF: {type(exc).__name__}: {exc}")
            return []

        return found

    @staticmethod
    def _ask(model: str, base_url: str, image: str) -> list[str]:
        """Один запрос к зрительной модели. Возвращает строки-заголовки."""
        payload = json.dumps(
            {
                "model": model,
                "prompt": PROMPT,
                "images": [image],
                # Ноль, а не 0.5: здесь не нужно разнообразие, нужна точность
                # повторения. Замер на этой же странице дал верные заголовки
                # именно при нуле.
                "options": {"temperature": 0},
                "stream": False,
            }
        ).encode()

        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            # Модель грузится в видеопамять: на карте 8 ГБ это десятки секунд.
            with urllib.request.urlopen(request, timeout=600) as response:
                answer = json.loads(response.read().decode()).get("response", "")
        except urllib.error.URLError as exc:
            raise CommandError(f"модель недоступна: {exc}") from exc

        lines = []
        for raw in answer.splitlines():
            line = raw.strip().lstrip("-•*").strip()
            # Модель любит обернуть ответ в блок кода — это не заголовок.
            if not line or line.startswith("```"):
                continue
            lines.append(line)
        return lines
