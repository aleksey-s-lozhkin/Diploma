"""Нарезка документа на куски.

Отдельного внимания здесь заслуживают две вещи, которые ломаются тихо.

Первая — **размер куска**. Кусок вдвое больше задуманного не даёт ошибки:
он просто хуже ищется, потому что вектор размывается. Поэтому размер
проверяется у всех кусков, а не у первого.

Вторая — **смещения**. Они нужны, чтобы показать человеку место в
документе. Смещение, посчитанное от очищенного текста вместо исходного,
указывает мимо, и заметить это можно только сравнением — чем тесты и
занимаются.
"""

from documents.chunking import (
    MIN_CHARS,
    TARGET_CHARS,
    Chunk,
    split_into_chunks,
)

PARAGRAPHS = "\n\n".join(f"Абзац номер {index}. " + "Слово " * 60 for index in range(12))


class TestEmpty:
    """Пустое на входе — пустое на выходе."""

    def test_empty_text_gives_nothing(self):
        assert split_into_chunks("") == []

    def test_whitespace_only_gives_nothing(self):
        assert split_into_chunks("   \n\t\n  ") == []


class TestShortText:
    """Короткий текст — это один кусок, а не ноль."""

    def test_short_note_becomes_one_chunk(self):
        """Заметка короче куска всё равно должна находиться.

        Ноль кусков означал бы, что документ загрузили, а найти его
        нельзя, — и человек не понял бы, почему.
        """
        note = "Короткая заметка про Docker."
        chunks = split_into_chunks(note)
        assert len(chunks) == 1
        assert chunks[0].text == note

    def test_text_exactly_at_the_limit_is_one_chunk(self):
        text = "я" * TARGET_CHARS
        assert len(split_into_chunks(text)) == 1


class TestSize:
    """Размер кусков."""

    def test_no_chunk_exceeds_the_target(self):
        for chunk in split_into_chunks(PARAGRAPHS):
            assert len(chunk.text) <= TARGET_CHARS

    def test_solid_text_without_blank_lines_is_split(self):
        """Сплошной текст без пустых строк тоже режется.

        Иначе один абзац на десять тысяч знаков стал бы одним куском, и
        поиск по нему не нашёл бы ничего осмысленного.
        """
        solid = "Это предложение. " * 400
        chunks = split_into_chunks(solid)
        assert len(chunks) > 1
        assert all(len(chunk.text) <= TARGET_CHARS for chunk in chunks)

    def test_chunks_are_not_too_small(self):
        """Огрызков быть не должно: мелкий кусок только засоряет выдачу."""
        chunks = split_into_chunks(PARAGRAPHS)
        assert all(len(chunk.text) >= MIN_CHARS for chunk in chunks)


class TestContentIsPreserved:
    """Ничего не теряется и не режется посередине."""

    def test_words_survive_intact(self):
        """Слова не разрезаются: обрывок бесполезен и вектору, и человеку."""
        solid = "Это предложение. " * 400
        chunks = split_into_chunks(solid)
        joined = " ".join(chunk.text for chunk in chunks)
        assert set(solid.split()) <= set(joined.split())

    def test_every_chunk_is_non_empty(self):
        assert all(chunk.text.strip() for chunk in split_into_chunks(PARAGRAPHS))


class TestOverlap:
    """Перехлёст: куски перекрываются, но не совпадают."""

    def test_neighbouring_chunks_overlap(self):
        chunks = split_into_chunks(PARAGRAPHS)
        assert len(chunks) > 1
        for previous, following in zip(chunks, chunks[1:]):
            assert following.start < previous.end

    def test_chunks_are_not_identical(self):
        """Перехлёст не должен съедать сам кусок."""
        chunks = split_into_chunks(PARAGRAPHS)
        texts = [chunk.text for chunk in chunks]
        assert len(set(texts)) == len(texts)


class TestOffsets:
    """Смещения указывают на настоящее место в тексте."""

    def test_offsets_are_inside_the_text(self):
        for chunk in split_into_chunks(PARAGRAPHS):
            assert 0 <= chunk.start < chunk.end <= len(PARAGRAPHS)

    def test_offsets_point_at_the_right_place(self):
        """Смещение ведёт туда, где кусок действительно начинается.

        Именно эта проверка ловит смещения, посчитанные от очищенного
        текста: они сдвинуты на длину отброшенных пробелов и указывают
        мимо, а выглядит это правдоподобно.
        """
        text = "\n\n   " + PARAGRAPHS
        for chunk in split_into_chunks(text):
            head = chunk.text[:40].strip()
            assert text[chunk.start : chunk.start + 40].strip().startswith(head[:20])

    def test_leading_whitespace_does_not_shift_offsets(self):
        plain = split_into_chunks(PARAGRAPHS)
        padded = split_into_chunks("\n\n   " + PARAGRAPHS)
        assert [c.start for c in padded] == [c.start + 5 for c in plain]

    def test_indexes_go_in_order(self):
        chunks = split_into_chunks(PARAGRAPHS)
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


class TestArguments:
    """Неподходящие параметры отвергаются сразу."""

    def test_zero_target_is_refused(self):
        try:
            split_into_chunks("текст", target=0)
        except ValueError:
            return
        raise AssertionError("нулевая цель должна быть отвергнута")

    def test_negative_overlap_is_refused(self):
        try:
            split_into_chunks("текст", overlap=-1)
        except ValueError:
            return
        raise AssertionError("отрицательный перехлёст должен быть отвергнут")

    def test_overlap_not_smaller_than_target_is_refused(self):
        """Иначе нарезка не сойдётся: каждый следующий кусок равен прежнему."""
        try:
            split_into_chunks("текст", target=100, overlap=100)
        except ValueError:
            return
        raise AssertionError("перехлёст не меньше цели должен быть отвергнут")

    def test_small_target_still_produces_chunks(self):
        chunks = split_into_chunks("Предложение раз. Предложение два. " * 40, target=120, overlap=20)
        assert chunks
        assert all(isinstance(chunk, Chunk) for chunk in chunks)
