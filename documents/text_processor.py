import re

import spacy

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("ru_core_news_sm", disable=["ner", "parser"])
        _nlp.max_length = 2_000_000
    return _nlp


def merge_split_words(doc):
    """Объединяет разорванные слова на основе анализа spacy"""
    tokens = list(doc)
    merged = []
    i = 0

    while i < len(tokens):
        token = tokens[i]

        if i + 1 < len(tokens):
            next_token = tokens[i + 1]

            if (
                len(token.text) < 5
                and len(next_token.text) < 8
                and token.is_alpha
                and next_token.is_alpha
                and not next_token.is_sent_start
            ):
                merged.append(token.text + next_token.text)
                i += 2
                continue

        merged.append(token.text)
        i += 1

    return " ".join(merged)


def clean_extracted_text(text: str) -> str:
    """Улучшенная очистка текста с использованием spacy"""
    if not text:
        return ""

    # Предварительная очистка
    text = text.replace("\x00", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Обработка с помощью spacy
    if len(text) > 1000:
        try:
            nlp = get_nlp()
            doc = nlp(text[:500000])
            text = merge_split_words(doc)
        except Exception as e:
            print(f"Spacy failed: {e}")

    # Финальная чистка
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()
