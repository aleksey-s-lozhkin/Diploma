"""Замер RAG-пути: тот же поиск, что отдаётся Самогону и лаптю.

Отличие от `measure_search.py` принципиальное. Тот меряет **веб-поиск**,
который ищет по целым документам. Здесь — **путь потребителей**: индекс
`chunks`, отрывки, `operator="and"`. Это то, что получит Семён, когда гость
спросит «как деплоить проект».

Мерим **его же кодом** (`_build_search` и `_collect` из вью), а не копией
запроса: копия разойдётся с оригиналом, и замер начнёт врать.
"""

import json
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from documents.models import ApiToken  # noqa: E402
from documents.views.views_retrieve import RetrieveView  # noqa: E402

#: Вопрос и начало имени документа, где лежит ответ. Те же, что в веб-замере,
#: чтобы результаты можно было сравнивать построчно.
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

TOP_K = 5


def main() -> int:
    token = ApiToken.objects.filter(scope=ApiToken.SCOPE_PERSONAL).first()
    if token is None:
        token = ApiToken.objects.first()
    if token is None:
        print("нет ни одного токена — замер невозможен")
        return 2

    view = RetrieveView()
    rows = []

    for query, expected, kind in QUESTIONS:
        try:
            search = view._build_search(token, query, None, TOP_K * 3)
            response = search.execute()
            collected = view._collect(response, TOP_K * 3)
        except Exception as exc:  # индекс может быть не создан — это не «не нашлось»
            rows.append(
                {
                    "query": query,
                    "kind": kind,
                    "expected": expected,
                    "position": 0,
                    "found_total": -1,
                    "error": f"{type(exc).__name__}: {exc}",
                    "top": [],
                }
            )
            continue

        titles = [item.get("title") or "" for item in collected]  # noqa: E501
        position = 0
        for index, title in enumerate(titles, start=1):
            if expected.lower() in str(title).lower():
                position = index
                break

        rows.append(
            {
                "query": query,
                "kind": kind,
                "expected": expected,
                "position": position,
                "found_total": len(collected),
                "top": titles[:3],
            }
        )

    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
