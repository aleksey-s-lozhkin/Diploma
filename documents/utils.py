import PyPDF2
from docx import Document as DocxDocument
from openpyxl import load_workbook


def extract_text_from_file(file_path, file_type):
    """Извлекает текст из PDF, DOCX, XLSX файлов"""
    text = ""

    if file_type == "pdf":
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"

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

    return text
