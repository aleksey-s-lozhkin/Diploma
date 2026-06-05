import os
import tempfile
from unittest.mock import MagicMock, patch

from django.test import TestCase

from documents.utils import extract_text_from_file


class ExtractTextFromFileTest(TestCase):
    """Тесты для extract_text_from_file"""

    def test_extract_text_from_pdf_success(self):
        """Успешное извлечение текста из PDF"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4\ntest")
            tmp_path = tmp.name

        try:
            with patch("pypdf.PdfReader") as mock_reader:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "Extracted PDF text"
                mock_reader.return_value.pages = [mock_page, mock_page]

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
            with patch("pypdf.PdfReader") as mock_reader:
                mock_page = MagicMock()
                # Текст с множественными переносами
                mock_page.extract_text.return_value = "Line 1\n\n\n\nLine 2"
                mock_reader.return_value.pages = [mock_page]

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
            with patch("pypdf.PdfReader") as mock_reader:
                mock_reader.side_effect = Exception("PDF read error")

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
