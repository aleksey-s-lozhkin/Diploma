"""Общие ограничения и проверки для документов.

Раньше одни и те же числа были продублированы в views_web.py, views_api.py и
serializers.py, а web-форма не проверяла тип файла вообще — API проверял. Здесь
единственное место, где описаны правила.
"""

MAX_TEXT_LENGTH = 100_000
MAX_RUBRICS = 10
MAX_RUBRIC_LENGTH = 100
MAX_FILE_SIZE = 20 * 1024 * 1024  # совпадает с client_max_body_size в nginx

#: Сколько знаков считаем признаком текстового слоя в файле. Скан даёт
#: колонтитул и пару строк: на нашем корпусе такой PDF дал 47 знаков на семь
#: страниц. Такой документ честнее показать как «текст не извлёкся».
MIN_EXTRACTED_CHARS = 200
ALLOWED_FILE_TYPES = ("pdf", "docx", "xlsx", "txt", "md", "py")


class DocumentValidationError(ValueError):
    """Нарушение правил документа. Сообщение показывается пользователю."""


def normalize_rubrics(raw) -> list:
    """Приводит рубрики к списку строк.

    Принимает и список (JSON API), и строку через запятую (web-форма).
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = raw
    else:
        raise DocumentValidationError("Рубрики должны быть списком или строкой через запятую")

    rubrics = []
    for item in items:
        if not isinstance(item, str):
            raise DocumentValidationError("Рубрики должны быть строками")
        rubric = item.strip()
        if rubric:
            rubrics.append(rubric)

    if len(rubrics) > MAX_RUBRICS:
        raise DocumentValidationError(f"Не более {MAX_RUBRICS} рубрик")
    for rubric in rubrics:
        if len(rubric) > MAX_RUBRIC_LENGTH:
            raise DocumentValidationError(
                f"Рубрика '{rubric[:50]}…' слишком длинная: максимум {MAX_RUBRIC_LENGTH} символов"
            )
    return rubrics


def validate_uploaded_file(uploaded_file) -> str:
    """Проверяет загруженный файл и возвращает его тип.

    Проверка общая для web-формы и API: раньше форма принимала что угодно, а
    API ограничивался списком типов.
    """
    if not uploaded_file:
        raise DocumentValidationError("Файл не передан")

    name = uploaded_file.name or ""
    if "." not in name:
        raise DocumentValidationError(f"Не удалось определить тип файла. Разрешены: {', '.join(ALLOWED_FILE_TYPES)}")

    file_type = name.rsplit(".", 1)[-1].lower()
    if file_type not in ALLOWED_FILE_TYPES:
        raise DocumentValidationError(f"Неподдерживаемый тип файла. Разрешены: {', '.join(ALLOWED_FILE_TYPES)}")

    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_FILE_SIZE:
        raise DocumentValidationError(f"Файл больше {MAX_FILE_SIZE // (1024 * 1024)} МБ")

    return file_type


def parse_positive_int(value, default: int = 1) -> int:
    """Преобразует параметр запроса в положительное число.

    int() на пустой строке падал с ValueError и отдавал 500: `?page=` приходит
    от ботов и от пагинации с пустым значением.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 1 else default
