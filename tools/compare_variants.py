"""Сравнение вариантов поиска отрывков: один прогон — одна таблица.

Запускается **внутри контейнера** `diploma-web` (только там есть доступ к
Elasticsearch и к самому проекту):

    docker exec -w /app -e PYTHONPATH=/app diploma-web python /tmp/compare_variants.py

Зачем это, а не «просто добавить вектора». У поиска несколько ручек, и
заранее неизвестно, какая решает задачу. Полнотекст можно ослабить
(`operator`, `minimum_should_match`), можно добавить вектора, можно сложить
одно с другим. **Каждый вариант стоит времени, и выбрать надо замером.**

## Метрика одна: правильный документ в топ-3

Никаких «средних очков». Очки BM25 и косинус **несравнимы** — разные шкалы,
и среднее по ним не значит ничего (об этом же в `docs/ARCHITECTURE.md`).

## Два набора вопросов

* **дословные** — слова вопроса есть в тексте. Полнотекст находит их
  идеально, и **ломать это нельзя**;
* **перефразированные** — слова другие, смысл тот же. Ради них всё и
  затевается.

Без разделения «стало 12 из 15» не говорит, что улучшилось, а что сломалось.
"""

import json
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from elasticsearch_dsl import Q, Search, connections  # noqa: E402

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

#: Сколько отрывков берём на вариант и сколько считаем «попал».
FETCH = 20
TOP_K = 3

#: Имя поля с вектором. Задано при создании маппинга (`documents/documents.py`).
VECTOR_FIELD = "dense_vector"


def _visible(token) -> list:
    """Кому что видно — следствие токена, а не параметр запроса (§2 контракта)."""
    clauses = [Q("term", is_public=True)]
    if token.scope == ApiToken.SCOPE_PERSONAL and token.user_id:
        clauses.append(Q("term", user_id=token.user_id))
    return clauses


def _titles(search, limit=FETCH) -> list:
    """Заголовки первых `limit` попаданий обычного поиска."""
    titles = []
    for hit in search.execute():
        titles.append(getattr(hit, "title", "") or "")
        if len(titles) >= limit:
            break
    return titles


def _text_titles(token, query, index, *, operator, msm, size=FETCH) -> list:
    """Полнотекстовый поиск с заданными ручками."""
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
    search = search[:size]
    return _titles(search, size)


def _knn_titles(token, query, index, *, k=FETCH) -> list:
    """Векторный поиск как он реально работает в этом Elasticsearch.

    Три вещи, проверенные на живом индексе и **неочевидные**:

    1. `knn` — **не clause**, а параметр верхнего уровня. Через
       `search.query("knn", ...)` elasticsearch-dsl отвечает
       `UnknownDslObject`, а `.extra(knn=...)` роняет клиент: в замке
       версия 7.17, аргумент появился позже. Поэтому запрос идёт телом.
    2. **Фильтр обязан быть ВНУТРИ `knn`.** Проверено: с top-level `query`
       фильтр видимости не действует и возвращаются чужие куски. Для
       проекта, где изоляция документов держится на ADR-0001, это не
       мелочь, а прямой доступ к чужому.
    3. В `_source` просим только заголовок: тянем два десятка кусков по
       1,8 КБ, а нужен из них один заголовок.
    """
    from documents.services.embedding_service import embed_query

    body = {
        "knn": {
            "field": VECTOR_FIELD,
            "query_vector": embed_query(query),
            "k": k,
            "num_candidates": max(k * 10, 100),
            "filter": {
                "bool": {
                    "should": [clause.to_dict() for clause in _visible(token)],
                    "minimum_should_match": 1,
                }
            },
        },
        "_source": ["title"],
        "size": k,
    }
    response = connections.get_connection().search(index=index, body=body)
    return [(hit.get("_source") or {}).get("title") or "" for hit in response["hits"]["hits"]]


def _rrf(lists: list, *, k: int = 60) -> list:
    """Слияние по рангам (Reciprocal Rank Fusion).

    Почему по рангам, а не по очкам: BM25 и косинус живут на **разных
    шкалах**, и складывать их напрямую — складывать метры с килограммами.
    RRF складывает `1 / (k + место)`, то есть **места**, и нормировка не
    нужна вовсе.
    """
    scores: dict = {}
    for ranked in lists:
        for rank, title in enumerate(ranked, start=1):
            if not title:
                continue
            scores[title] = scores.get(title, 0.0) + 1.0 / (k + rank)
    return [title for title, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def _weighted(text: list, knn: list, *, alpha: float) -> list:
    """Слияние по очкам с нормировкой — для сравнения с RRF.

    Очки нормируются в [0, 1] **внутри своего списка**: сравнивать
    абсолютные значения нельзя, но относительные в пределах одного запроса
    осмысленны. `alpha` — вес полнотекста, `1 - alpha` — вес векторов.
    """

    def norm(items):
        total = max(len(items), 1)
        return {title: (total - rank) / total for rank, title in enumerate(items, 1) if title}

    left, right = norm(text), norm(knn)
    scores: dict = {}
    for title in set(left) | set(right):
        scores[title] = alpha * left.get(title, 0.0) + (1 - alpha) * right.get(title, 0.0)
    return [title for title, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def _position(titles: list, expected: str) -> int:
    """Место правильного документа в топ-3; 0 — не найден."""
    for at, title in enumerate(titles[:TOP_K], start=1):
        if expected.lower() in str(title).lower():
            return at
    return 0


def _variants(token, index):
    """Варианты из плана. Состав менять нельзя — он согласован."""

    def loose(query):
        return _text_titles(token, query, index, operator="or", msm="50%")

    def strict(query):
        return _text_titles(token, query, index, operator="and", msm="70%")

    def vectors(query):
        return _knn_titles(token, query, index)

    return {
        "bm25_and": strict,
        "bm25_or": lambda q: _text_titles(token, q, index, operator="or", msm="70%"),
        "bm25_loose": loose,
        "knn_only": vectors,
        # Строгий полнотекст рядом с векторами — проверить, не мешает ли он.
        "hybrid_rrf_strict": lambda q: _rrf([strict(q), vectors(q)]),
        "hybrid_rrf_loose": lambda q: _rrf([loose(q), vectors(q)]),
        "hybrid_weighted": lambda q: _weighted(loose(q), vectors(q), alpha=0.5),
    }


def main() -> int:
    index = os.environ.get("COMPARE_INDEX", "chunks")
    token = ApiToken.objects.filter(scope=ApiToken.SCOPE_PERSONAL).first() or ApiToken.objects.first()
    if token is None:
        print("нет ни одного токена — сравнение невозможно")
        return 2

    variants = _variants(token, index)
    results = {}
    detail = {}

    for name, run in variants.items():
        hits = {}
        for query, expected, kind in QUESTIONS:
            try:
                titles = run(query)
            except Exception as exc:  # noqa: BLE001
                hits[query] = (kind, 0, f"{type(exc).__name__}: {exc}")
                continue
            hits[query] = (kind, _position(titles, expected), None)
        detail[name] = hits

        score = {}
        for kind in ("literal", "paraphrase"):
            sub = [v for v in hits.values() if v[0] == kind]
            score[kind] = sum(1 for v in sub if v[1] > 0)
            score[kind + "_total"] = len(sub)
        score["total"] = score["literal"] + score["paraphrase"]
        score["total_all"] = score["literal_total"] + score["paraphrase_total"]
        results[name] = score

    print()
    print(f"  {'вариант':<22} {'дословные':>10} {'перефраз.':>10} {'всего':>8}   индекс={index}")
    print("  " + "─" * 64)
    for name, score in results.items():
        print(
            f"  {name:<22} {score['literal']:>3}/{score['literal_total']:<6} "
            f"{score['paraphrase']:>3}/{score['paraphrase_total']:<6} "
            f"{score['total']:>3}/{score['total_all']:<4}"
        )

    print("\n  Перефразированные построчно (место правильного; «—» = не найден):")
    names = list(results)
    print(f"    {'вопрос':<40} " + " ".join(f"{n[:13]:>14}" for n in names))
    for query, _expected, kind in QUESTIONS:
        if kind != "paraphrase":
            continue
        cells = []
        for name in names:
            position = detail[name][query][1]
            cells.append(f"{'#' + str(position) if position else '—':>14}")
        print(f"    {query[:38]:<40} " + " ".join(cells))

    errors = {
        name: {q: v[2] for q, v in hits.items() if v[2]}
        for name, hits in detail.items()
        if any(v[2] for v in hits.values())
    }
    if errors:
        print("\n  Ошибки выполнения:")
        for name, items in errors.items():
            for query, message in list(items.items())[:2]:
                print(f"    {name} / {query[:28]}: {message[:90]}")

    print("\n  Машиночитаемо:")
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
