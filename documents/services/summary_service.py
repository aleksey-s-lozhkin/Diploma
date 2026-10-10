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
#: Для дословного отрывка берётся **та же модель**, что и везде.
#:
#: Замер показывал, что меньшая `qwen3:4b-instruct` тут и быстрее (2,7 с
#: против 7,3 с), и точнее. Но у неё есть цена, которой в том замере не
#: было: **на видеокарте 8 ГБ две модели не помещаются**.
#:
#:     qwen3:8b при ctx 8192   6,19 ГБ
#:     qwen3:4b-instruct       3,18 ГБ в видеопамяти
#:                            ─────────
#:                            9,37 ГБ  при 8 ГБ на карте
#:
#: Загружая меньшую, сервис вытесняет общую — и следующий гость Самогона
#: или человек в лапте ждёт двадцать секунд загрузки. Это дороже, чем
#: четыре с половиной секунды на отрывке, тем более что отрывок кешируется
#: в Redis на сутки, а вытеснение бьёт по каждому обращению.
#:
#: Условие записано в lapot/docs/decisions/0010: одна модель на всех,
#: различия — параметрами запроса, а не файлами моделей.
DEFAULT_FRAGMENT_MODEL = "qwen3:8b"
DEFAULT_TIMEOUT = 90
DEFAULT_TEXT_LIMIT = 6000


def _setting(name, default):
    return getattr(settings, name, default)


def is_enabled() -> bool:
    """Настроена ли модель. Пустой адрес — выключено."""
    return bool(_setting("OLLAMA_URL", ""))


def _ask_model(prompt: str, model: str = None, as_json: bool = True) -> str:
    """Запрос к Ollama. Возвращает сырой ответ модели."""
    payload = {
        "model": model or _setting("OLLAMA_MODEL", DEFAULT_MODEL),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2 if as_json else 0.0},
    }
    if as_json:
        # Просим строгий JSON: разбирать прозу с вкраплениями JSON — лишняя работа.
        payload["format"] = "json"

    request = urllib.request.Request(
        f"{_setting('OLLAMA_URL', '').rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
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


FRAGMENT_PROMPT = """Ниже текст документа. Найди в нём и верни ДОСЛОВНО одну-две фразы, которые отвечают на запрос.
Верни только этот отрывок, без пояснений, без кавычек и без своих слов.

Запрос: {query}

Текст:
{text}"""


def verify_fragment(answer: str, text: str) -> str:
    """Оставить отрывок, только если он дословно есть в тексте.

    Модель дописывает и склеивает: на замере большая модель один раз из двух
    вернула фразу, которой в документе нет. Проверка детерминированная — ищем
    ответ в тексте, и всё, чего там нет, отбрасываем.
    """
    flat_answer = " ".join((answer or "").split()).strip(" \"'«»")
    flat_text = " ".join((text or "").split())

    if len(flat_answer) < 15 or flat_answer not in flat_text:
        return ""
    return flat_answer[:600]


def answer_fragment(text: str, query: str) -> str:
    """Отрывок, отвечающий на запрос. Пустая строка, если не получилось."""
    if not is_enabled() or len((text or "").strip()) < 200 or len((query or "").strip()) < 3:
        return ""

    limit = _setting("SUMMARY_TEXT_LIMIT", DEFAULT_TEXT_LIMIT)
    prompt = FRAGMENT_PROMPT.format(query=query, text=text[:limit])
    model = _setting("OLLAMA_FRAGMENT_MODEL", DEFAULT_FRAGMENT_MODEL)

    try:
        answer = _ask_model(prompt, model=model, as_json=False)
    # TimeoutError и URLError — подклассы OSError, отдельно их перечислять нечего.
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("Отрывок не получен: %s", exc)
        return ""

    return verify_fragment(_parse(answer)[0] or answer, text)
