import logging
import re

import pypdf
from docx import Document as DocxDocument
from openpyxl import load_workbook

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path, file_type):
    """Извлекает текст из PDF, DOCX, XLSX, TXT файлов"""
    text = ""

    try:
        if file_type == "pdf":
            with open(file_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            # Минимальная очистка — только множественные переносы
            text = re.sub(r"\n{3,}", "\n\n", text)

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

    return text
