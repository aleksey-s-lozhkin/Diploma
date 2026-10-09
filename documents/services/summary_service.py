"""Описание и теги документа от языковой модели.

Зачем: извлечённый из PDF текст не даёт понять, о чём документ, — в карточке
видно обрывок вроде «Типы данных 1 Типы данных Объявляем переменную». Модель
читает текст и возвращает одно-два предложения и десяток тегов.

Всё здесь **best-effort**: недоступная модель не должна ломать ни загрузку
документа, ни поиск. Ошибка возвращает пустой результат и попадает в журнал.

HTTP — через стандартную библиотеку: тянуть ради одного запроса зависимость и
пересобирать замок не стоит.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

#: Сколько тегов просить и сколько принимать. Десять хватает для карточки.
MAX_KEYWORDS = 10

PROMPT = """Ты помогаешь описать документ в поисковой системе.

Верни ТОЛЬКО JSON без пояснений:
{{"summary": "одно-два предложения", "keywords": ["тег", "тег"]}}

Требования:
- summary: о чём документ, по-русски, простыми словами. Только по тексту ниже, без выдумок и без вступлений вроде «в этом документе».
- keywords: от 5 до {keywords} коротких тегов — термины, технологии, темы. Без знака #. Если термин принято писать по-английски (python, dict), пиши по-английски.

Текст документа:
{text}"""


#: Значения по умолчанию: набор настроек зависит от окружения (в проверках он
#: свой), и сервис не должен падать из-за отсутствующей переменной.
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_TIMEOUT = 90
DEFAULT_TEXT_LIMIT = 6000


def _setting(name, default):
    return getattr(settings, name, default)


def is_enabled() -> bool:
    """Настроена ли модель. Пустой адрес — выключено."""
    return bool(_setting("OLLAMA_URL", ""))


def _ask_model(prompt: str) -> str:
    """Запрос к Ollama. Возвращает сырой ответ модели."""
    payload = json.dumps(
        {
            "model": _setting("OLLAMA_MODEL", DEFAULT_MODEL),
            "prompt": prompt,
            "stream": False,
            # Просим строгий JSON: разбирать прозу с вкраплениями JSON — лишняя работа.
            "format": "json",
            "options": {"temperature": 0.2},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{_setting('OLLAMA_URL', '').rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_setting("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body.get("response", "")


def _parse(answer: str):
    """Разобрать ответ модели. Модель может обернуть JSON в текст — ищем скобки."""
    try:
        data = json.loads(answer)
    except json.JSONDecodeError:
        start, end = answer.find("{"), answer.rfind("}")
        if start == -1 or end == -1:
            return "", []
        try:
            data = json.loads(answer[start : end + 1])
        except json.JSONDecodeError:
            return "", []

    summary = str(data.get("summary") or "").strip()
    keywords = [str(item).strip().lstrip("#") for item in (data.get("keywords") or []) if str(item).strip()]
    return summary, keywords[:MAX_KEYWORDS]


def summarize_text(text: str):
    """Описание и теги для текста. Без обращений к базе: удобно проверять."""
    if not is_enabled() or len((text or "").strip()) < 200:
        return "", []

    limit = _setting("SUMMARY_TEXT_LIMIT", DEFAULT_TEXT_LIMIT)
    prompt = PROMPT.format(keywords=MAX_KEYWORDS, text=text[:limit])
    try:
        answer = _ask_model(prompt)
    # TimeoutError и URLError — подклассы OSError, отдельно их перечислять нечего.
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("Описание не получено: %s", exc)
        return "", []

    return _parse(answer)


def summarize_document(document) -> bool:
    """Обновить описание и теги документа. Возвращает True, если что-то изменилось."""
    summary, keywords = summarize_text(document.text)
    if not summary and not keywords:
        return False

    document.summary = summary
    document.keywords = keywords
    document.save(update_fields=["summary", "keywords"])
    logger.info("Документ %s: описание получено (%s тегов)", document.pk, len(keywords))
    return True
