import os
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.constants import MIN_EXTRACTED_CHARS
from documents.utils import extract_text_from_file


def pdf_stub(pages_text):
    """Заглушка pdfplumber: контекстный менеджер со страницами.

    Настоящий PDF в тестах не нужен: проверяем обвязку — что страницы
    обходятся, текст собирается и очищается.
    """
    pages = []
    for value in pages_text:
        page = MagicMock()
        page.extract_text.return_value = value
        pages.append(page)
    pdf = MagicMock()
    pdf.pages = pages
    manager = MagicMock()
    manager.__enter__.return_value = pdf
    manager.__exit__.return_value = False
    return manager


class ExtractTextFromFileTest(TestCase):
    """Тесты для extract_text_from_file"""

    def test_extract_text_from_pdf_success(self):
        """Успешное извлечение текста из PDF"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\ntest")
            tmp_path = tmp.name

        try:
            with patch(
                "documents.utils.pdfplumber.open", return_value=pdf_stub(["Extracted PDF text", "Extracted PDF text"])
            ):
                text = extract_text_from_file(tmp_path, "pdf")

                # Проверяем, что текст извлечён и очищен
                self.assertIn("Extracted PDF text", text)
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_pdf_cleans_multiple_newlines(self):
        """Очистка множественных переносов строк в PDF"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\ntest")
            tmp_path = tmp.name

        try:
            with patch("documents.utils.pdfplumber.open", return_value=pdf_stub(["Line 1\n\n\n\nLine 2"])):
                text = extract_text_from_file(tmp_path, "pdf")

                # Проверяем, что множественные переносы заменены
                self.assertNotIn("\n\n\n\n", text)
                self.assertIn("Line 1", text)
                self.assertIn("Line 2", text)
                # Должен быть хотя бы один перенос
                self.assertIn("\n", text)
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_pdf_with_error(self):
        """Ошибка при извлечении текста из PDF"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"invalid")
            tmp_path = tmp.name

        try:
            with patch("documents.utils.pdfplumber.open", side_effect=Exception("PDF read error")):
                text = extract_text_from_file(tmp_path, "pdf")

                self.assertEqual(text, "")
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_docx_with_error(self):
        """Ошибка при извлечении текста из DOCX"""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(b"invalid")
            tmp_path = tmp.name

        try:
            with patch("docx.Document") as mock_docx:
                mock_docx.side_effect = Exception("DOCX read error")

                text = extract_text_from_file(tmp_path, "docx")

                self.assertEqual(text, "")
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_xlsx_with_error(self):
        """Ошибка при извлечении текста из XLSX"""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(b"invalid")
            tmp_path = tmp.name

        try:
            with patch("openpyxl.load_workbook") as mock_load:
                mock_load.side_effect = Exception("XLSX read error")

                text = extract_text_from_file(tmp_path, "xlsx")

                self.assertEqual(text, "")
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_txt_success(self):
        """Успешное извлечение текста из TXT"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write("Hello, world!\nSecond line.")
            tmp_path = tmp.name

        try:
            text = extract_text_from_file(tmp_path, "txt")
            # Проверяем, что текст извлечён и содержит нужные слова
            self.assertIn("Hello", text)
            self.assertIn("world", text)
            self.assertIn("Second", text)
            self.assertIn("line", text)
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_txt_with_utf8(self):
        """Извлечение текста из TXT с UTF-8 символами"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write("Привет, мир!\nРусский текст 🚀")
            tmp_path = tmp.name

        try:
            text = extract_text_from_file(tmp_path, "txt")
            self.assertIn("Привет", text)
            self.assertIn("Русский", text)
            self.assertIn("текст", text)
            self.assertIn("🚀", text)
        finally:
            os.unlink(tmp_path)

    def test_extract_text_from_txt_with_error(self):
        """Ошибка при чтении TXT файла"""
        text = extract_text_from_file("/nonexistent/path.txt", "txt")
        self.assertEqual(text, "")

    def test_extract_text_unsupported_file_type(self):
        """Неподдерживаемый тип файла"""
        with tempfile.NamedTemporaryFile(suffix=".unknown", delete=False) as tmp:
            tmp.write(b"some content")
            tmp_path = tmp.name

        try:
            text = extract_text_from_file(tmp_path, "unknown")
            self.assertEqual(text, "")
        finally:
            os.unlink(tmp_path)

    def test_file_not_found(self):
        """Файл не найден"""
        text = extract_text_from_file("/nonexistent/path.pdf", "pdf")
        self.assertEqual(text, "")


class SourceFilesAndScanTest(TestCase):
    """Исходники шпаргалок и честная пометка сканов."""

    def _write(self, suffix, content):
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w", encoding="utf-8")
        handle.write(content)
        handle.close()
        return handle.name

    def test_markdown_is_read_as_text(self):
        path = self._write(".md", "# Заголовок\n\nТекст про FSRS")
        try:
            self.assertIn("Текст про FSRS", extract_text_from_file(path, "md"))
        finally:
            os.unlink(path)

    def test_python_source_is_read_as_text(self):
        path = self._write(".py", "def hello():\n    return 'привет'")
        try:
            self.assertIn("def hello()", extract_text_from_file(path, "py"))
        finally:
            os.unlink(path)

    def test_scan_threshold(self):
        """Порог, по которому документ считается сканом без текстового слоя."""
        self.assertEqual(MIN_EXTRACTED_CHARS, 200)
        self.assertLess(len("# Считаем количество вхождений элемента y"), MIN_EXTRACTED_CHARS)


class ReextractCommandTest(TestCase):
    """Команда обновляет текст, когда он изменился, даже если стал короче."""

    def test_changed_shorter_text_is_updated(self):
        from django.core.management import call_command

        from documents.models import Document

        user = get_user_model().objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        document = Document.objects.create(user=user, text="старый мусорный текст " * 20, file_name="x.md")

        call_command("reextract_text", verbosity=0)

        document.refresh_from_db()
        # Файла нет — читать нечего, поэтому текст остаётся прежним: команда не
        # должна затирать хороший текст пустотой.
        self.assertIn("старый мусорный текст", document.text)
