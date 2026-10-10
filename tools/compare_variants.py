"""Сравнение вариантов поиска отрывков: один прогон — одна таблица.

Запускается **внутри контейнера** `diploma-web` (только там есть доступ к
Elasticsearch и к самому проекту):

    docker exec -w /app -e PYTHONPATH=/app diploma-web python /tmp/compare_variants.py

Зачем это, а не «просто добавить вектора». У поиска есть несколько ручек,
и заранее неизвестно, какая из них решает задачу. Полнотекст можно ослабить
(`operator`, `minimum_should_match`), можно добавить вектора, можно сложить
одно с другим. **Каждый вариант стоит времени, и выбрать надо замером.**

## Метрика одна: правильный документ в топ-3

Никаких «средних очков». Очки BM25 и косинус **несравнимы** — разные шкалы,
и среднее по ним не значит ничего (об этом же сказано в
`docs/ARCHITECTURE.md`). Считаем попадания, и только их.

## Два набора вопросов

* **дословные** — слова вопроса есть в тексте. Их полнотекст находит
  идеально, и **ломать это нельзя**: вариант, который выиграл на
  перефразированных, но потерял дословные, не годится;
* **перефразированные** — слова другие, смысл тот же. Ради них всё и
  затевается.

Разделение обязательно. Без него «стало 12 из 15» не говорит, что именно
улучшилось, а что сломалось.
"""

import json
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from elasticsearch_dsl import Search  # noqa: E402

from documents.models import ApiToken  # noqa: E402

#: Вопросы и ожидаемые документы. **Взяты из `measure_retrieve.py` и не
#: меняются:** подогнанный набор вопросов ничего не доказывает.
QUESTIONS = [
    ("конкатенация строк", "Строки", "literal"),
    ("лямбда-функции", "Продвинутые функции", "literal"),
    ("как объявить функцию def", "Базовые функции. Шпаргалка", "literal"),
    ("создание множества", "Множества", "literal"),
    ("перебор значений словаря", "Словари", "literal"),
    ("синтаксис цикла for in", "Циклы", "literal"),
    ("переменные типа bool", "Основы синтаксиса", "literal"),
    ("как определить длину строки", "Строки", "literal"),
    ("как склеить две строки", "Строки", "paraphrase"),
    ("как сделать короткую функцию без имени", "Продвинутые функции", "paraphrase"),
    ("как узнать сколько символов в слове", "Строки", "paraphrase"),
    ("как перебрать ключи и значения", "Словари", "paraphrase"),
    ("как повторить действие несколько раз", "Циклы", "paraphrase"),
    ("как вернуть значение из функции", "Конспект. Базовые функции", "paraphrase"),
    ("как убрать пробелы по краям строки", "Строки", "paraphrase"),
]

#: Сколько отрывков берём на вариант. Топ-3 считается по первым трём.
FETCH = 20
TOP_K = 3


def _visible(token) -> list:
    """Кому что видно — следствие токена, а не параметр запроса (§2 контракта)."""
    from elasticsearch_dsl import Q

    clauses = [Q("term", is_public=True)]
    if token.scope == ApiToken.SCOPE_PERSONAL and token.user_id:
        clauses.append(Q("term", user_id=token.user_id))
    return clauses


def _text_only(token, query, index, *, operator, msm):
    """Полнотекстовый вариант с заданными ручками."""
    search = Search(index=index)
    search = search.query(
        "multi_match",
        query=query,
        fields=["text^3", "title^2"],
        operator=operator,
        fuzziness="AUTO",
        minimum_should_match=msm,
    )
    search = search.query("bool", should=_visible(token), minimum_should_match=1)
    return search


def _knn_only(token, query, index, *, k=20):
    """Только вектора. Нужен `dense_vector` в маппинге и эмбеддинг запроса."""
    from documents.services.embedding_service import embed_text

    vector = embed_text(query)
    search = Search(index=index)
    search = search.query(
        "knn",
        field="embedding",
        query_vector=vector,
        k=k,
        num_candidates=max(k * 10, 100),
    )
    search = search.query("bool", should=_visible(token), minimum_should_match=1)
    return search


#: Варианты: имя → функция, строящая запрос. Порядок — как в плане.
VARIANTS = {
    "bm25_and": lambda t, q, i: _text_only(t, q, i, operator="and", msm="70%"),
    "bm25_or": lambda t, q, i: _text_only(t, q, i, operator="or", msm="70%"),
    "bm25_loose": lambda t, q, i: _text_only(t, q, i, operator="or", msm="50%"),
    # Варианты с векторами подключаются, когда есть эмбеддинги.
    "knn_only": lambda t, q, i: _knn_only(t, q, i),
}


def _run_variant_plain(token, name, factory, index) -> dict:
    """Вариант, который Elasticsearch выполняет одним запросом."""
    hits = {}
    for query, expected, kind in QUESTIONS:
        try:
            response = factory(token, query, index).execute()
        except Exception as exc:  # noqa: BLE001
            hits[query] = (kind, expected, 0, f"{type(exc).__name__}")
            continue

        titles = []
        for hit in response:
            titles.append(getattr(hit, "title", "") or "")
            if len(titles) >= TOP_K:
                break

        position = 0
        for at, title in enumerate(titles, start=1):
            if expected.lower() in str(title).lower():
                position = at
                break
        hits[query] = (kind, expected, position, None)
    return hits


def _score(hits: dict) -> dict:
    """Свести попадания в две строки: дословные и перефразированные."""
    out = {}
    for kind in ("literal", "paraphrase"):
        sub = [v for v in hits.values() if v[0] == kind]
        out[kind] = sum(1 for v in sub if 0 < v[2] <= TOP_K)
        out[kind + "_total"] = len(sub)
    out["total"] = out["literal"] + out["paraphrase"]
    out["total_all"] = out["literal_total"] + out["paraphrase_total"]
    return out


def main() -> int:
    index = os.environ.get("COMPARE_INDEX", "chunks")
    token = ApiToken.objects.filter(scope=ApiToken.SCOPE_PERSONAL).first() or ApiToken.objects.first()
    if token is None:
        print("нет ни одного токена — сравнение невозможно")
        return 2

    rows = []
    for name, factory in VARIANTS.items():
        hits = _run_variant_plain(token, name, factory, index)
        rows.append((name, _score(hits), hits))

    print()
    print(f"  {'вариант':<16} {'дословные':>10} {'перефраз.':>10} {'всего':>8}   индекс={index}")
    print("  " + "─" * 58)
    for name, score, _ in rows:
        print(
            f"  {name:<16} {score['literal']}/{score['literal_total']:>8} "
            f"{score['paraphrase']}/{score['paraphrase_total']:>8} "
            f"{score['total']}/{score['total_all']:>6}"
        )

    # Провальные вопросы: без этого таблица не говорит, ГДЕ стало лучше.
    print("\n  Провальные в базовом варианте (перефразированные):")
    baseline = rows[0][2] if rows else {}
    for query, expected, kind in QUESTIONS:
        if kind != "paraphrase":
            continue
        position = baseline.get(query, (kind, expected, 0, None))[2]
        if position == 0:
            marks = []
            for name, _, hits in rows:
                marks.append(f"{name}={'#' + str(hits[query][2]) if hits[query][2] else '—'}")
            print(f"    {query[:42]:<44} {'  '.join(marks)}")

    print("\n  Машиночитаемо:")
    print(
        json.dumps(
            {name: dict(score) for name, score, _ in rows},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
