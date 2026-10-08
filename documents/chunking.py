"""Нарезка документа на куски для поиска по смыслу.

Модуль намеренно **не зависит ни от чего**, кроме стандартной библиотеки.
Нарезка — это чистая работа с текстом, и держать её в стороне от Django и
Elasticsearch стоит по двум причинам: её можно проверить без поднятия
сервисов, и её правила видны целиком в одном файле, а не растворены по
обработчикам загрузки.

Зачем вообще нарезать
---------------------

Сейчас документ индексируется целиком, одним полем. Для полнотекстового
поиска этого достаточно: нашлась страница — показали страницу. Для поиска
по смыслу нет. Вектор одного большого текста — это усреднённый смысл всего
документа, и он почти не отличается от вектора любого другого документа на
ту же тему. Сравнивать такие векторы бессмысленно.

Поэтому документ режется на куски по несколько абзацев, у каждого свой
вектор, и поиск идёт по кускам. Найденный кусок потом показывается целиком
— человеку нужен контекст, а не обрывок.

Как выбирается размер
---------------------

В символах, а не в токенах: токенизатора здесь нет, а тянуть его ради
нарезки — лишняя зависимость. Для русского текста один токен — это
примерно два с половиной символа, поэтому границы пересчитаны из целевых
пятисот-тысячи токенов.

Перехлёст нужен потому, что мысль редко укладывается ровно в границу.
Если кусок обрывается на середине рассуждения, хвост предыдущего куска
даёт следующему начало, и поиск находит ответ независимо от того, в какой
кусок он попал.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Целевой размер куска в символах. Около семисот токенов: достаточно,
#: чтобы кусок содержал законченную мысль, и достаточно мало, чтобы вектор
#: не размывался.
TARGET_CHARS = 1800

#: Перехлёст между соседними кусками — примерно четырнадцать процентов.
#: Меньше — и мысль на границе теряется для обоих кусков; больше — и поиск
#: начинает выдавать почти одинаковые куски подряд.
OVERLAP_CHARS = 250

#: Кусок короче этого к соседям приклеивается: сам по себе он слишком мал,
#: чтобы нести смысл, а в выдаче занимает столько же места.
MIN_CHARS = 200

#: Абзац. Пустая строка разделяет смысловые блоки, и резать по ней
#: естественнее всего: заголовок, список и абзац остаются целыми.
_PARAGRAPH = re.compile(r"\n\s*\n")

#: Конец предложения: точка, вопросительный, восклицательный знак или
#: многоточие, за которыми следует пробел или конец строки. Используется
#: только тогда, когда один абзац не влезает в кусок целиком.
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class Chunk:
    """Кусок документа.

    :param text: сам текст куска.
    :param index: порядковый номер с нуля.
    :param start: смещение начала в исходном тексте.
    :param end: смещение конца.

    Смещения нужны, чтобы показать человеку, **откуда** кусок взят: без
    них найденный отрывок висит в воздухе, и проверить его нельзя.
    """

    text: str
    index: int
    start: int
    end: int


def _split_long(paragraph: str, limit: int) -> list[str]:
    """Разбить слишком длинный абзац по предложениям.

    Абзац может быть длиннее куска целиком — например, сплошной текст без
    пустых строк. Тогда режем по предложениям, а если и предложение не
    влезает (бывает в таблицах и списках без точек), режем по границе
    слова. Резать по символам нельзя: разрезанный посередине слова кусок
    бессмыслен и для вектора, и для человека.
    """
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE.split(paragraph):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        # Предложение само длиннее куска — режем по словам.
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        current = sentence
    if current:
        parts.append(current)
    return parts


def _paragraphs(text: str) -> list[tuple[str, int]]:
    """Разбить текст на абзацы, сохранив смещения.

    Смещения считаются по исходной строке, а не по очищенной: иначе они
    указывали бы в никуда, и показать место в документе было бы нельзя.
    """
    result: list[tuple[str, int]] = []
    position = 0
    for raw in _PARAGRAPH.split(text):
        stripped = raw.strip()
        if stripped:
            # Поиск с позиции, а не сначала: одинаковые абзацы должны
            # получить разные смещения, иначе все они укажут на первый.
            offset = text.index(stripped, position)
            result.append((stripped, offset))
            position = offset + len(stripped)
    return result


def split_into_chunks(
    text: str,
    *,
    target: int = TARGET_CHARS,
    overlap: int = OVERLAP_CHARS,
    minimum: int = MIN_CHARS,
) -> list[Chunk]:
    """Нарезать текст на куски с перехлёстом.

    Границы проводятся по абзацам: заголовок, список и абзац остаются
    целыми. Абзац длиннее куска режется по предложениям, а предложение
    длиннее куска — по словам.

    Пустой текст и текст короче ``minimum`` дают **один** кусок, а не ноль:
    короткая заметка — это тоже документ, и искать по ней нужно. Ноль
    кусков означал бы, что документ загрузили, а найти его нельзя.
    """
    if target <= 0:
        raise ValueError("target должен быть больше нуля")
    if overlap < 0:
        raise ValueError("overlap не может быть отрицательным")
    if overlap >= target:
        raise ValueError("overlap должен быть меньше target, иначе нарезка не сойдётся")

    cleaned = text.strip()
    if not cleaned:
        return []

    # Смещения считаются по исходному тексту, а не по очищенному: иначе
    # отброшенные пробелы сдвинули бы их, и показать место в документе
    # было бы нельзя. Ведущие пробелы отбрасываются один раз здесь.
    lead = len(text) - len(text.lstrip())
    if len(cleaned) <= target:
        return [Chunk(text=cleaned, index=0, start=lead, end=lead + len(cleaned))]

    # Абзацы длиннее куска разбиваются заранее, чтобы дальше работать
    # только с частями, каждая из которых помещается.
    pieces: list[tuple[str, int]] = []
    for paragraph, offset in _paragraphs(text):
        if len(paragraph) <= target:
            pieces.append((paragraph, offset))
            continue
        cursor = 0
        for part in _split_long(paragraph, target):
            found = paragraph.find(part, cursor)
            pieces.append((part, offset + max(found, 0)))
            cursor = max(found, 0) + len(part)

    chunks: list[Chunk] = []
    current: list[tuple[str, int]] = []
    size = 0

    def flush() -> None:
        """Записать накопленное и подготовить перехлёст для следующего."""
        nonlocal current, size
        if not current:
            return
        body = "\n\n".join(piece for piece, _ in current)
        chunks.append(
            Chunk(
                text=body,
                index=len(chunks),
                start=current[0][1],
                end=current[-1][1] + len(current[-1][0]),
            )
        )
        # Хвост уходит в начало следующего куска. Берём целые абзацы с
        # конца, пока не наберём перехлёст: разрезать абзац пополам ради
        # ровного числа символов незачем.
        tail: list[tuple[str, int]] = []
        taken = 0
        for piece in reversed(current):
            if taken >= overlap:
                break
            tail.insert(0, piece)
            taken += len(piece[0]) + 2
        current = tail
        size = taken

    for piece, offset in pieces:
        if size + len(piece) > target and current:
            flush()
            # Перехлёст не должен вытеснить сам кусок. Если после переноса
            # хвоста новый абзац всё равно не помещается, хвост укорачивается
            # с начала — иначе кусок вырастал бы почти вдвое против цели.
            while current and size + len(piece) > target:
                dropped = current.pop(0)
                size -= len(dropped[0]) + 2
        current.append((piece, offset))
        size += len(piece) + 2

    if current:
        flush()

    # Последний кусок может оказаться огрызком из-за перехлёста. Если он
    # мал настолько, что не несёт смысла, и есть предыдущий — вливаем его
    # туда, а не показываем отдельной строкой в выдаче.
    if len(chunks) > 1 and len(chunks[-1].text) < minimum:
        tail = chunks.pop()
        last = chunks[-1]
        chunks[-1] = Chunk(
            text=f"{last.text}\n\n{tail.text}",
            index=last.index,
            start=last.start,
            end=tail.end,
        )

    return chunks
