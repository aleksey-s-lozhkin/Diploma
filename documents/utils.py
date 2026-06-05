import logging
import re

import pypdf
from docx import Document as DocxDocument
from openpyxl import load_workbook

logger = logging.getLogger(__name__)


def clean_extracted_text(text):
    """Очищает извлечённый текст для улучшения поиска"""
    if not text:
        return ""

    # Заменяем NUL символы на пробелы
    text = text.replace("\x00", " ")

    # Убираем лишние пробелы (более одного подряд)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Нормализуем переносы строк (3+ переносов → 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Убираем пробелы в начале/конце строк
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def extract_text_from_file(file_path, file_type):
    """Извлекает текст из файла в зависимости от его типа. PDF, DOCX, XLSX, TXT"""
    text = ""

    try:
        if file_type == "pdf":
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

        elif file_type == "docx":
            doc = DocxDocument(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text += cell.text + " "
                    text += "\n"

        elif file_type == "xlsx":
            wb = load_workbook(file_path, data_only=True)
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    text += " ".join([str(cell) for cell in row if cell]) + "\n"

        elif file_type == "txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}", exc_info=True)
        return ""

    text = clean_extracted_text(text)

    return text
