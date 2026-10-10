"""Замер: находит ли поиск то, что должен.

Запускается внутри контейнера diploma-web — только там есть доступ к
Elasticsearch и к самому сервису поиска.

Смысл замера: у каждого вопроса есть **известный правильный документ**.
Мы не спрашиваем «нравится ли выдача», мы спрашиваем «на каком месте
оказался правильный». Это можно посчитать, и это нельзя подкрутить.

Вопросы двух видов:

* **дословные** — слова вопроса есть в документе. Их полнотекстовый поиск
  обязан находить, и если не находит, дело в настройках, а не в векторах;
* **перефразированные** — слова другие, смысл тот же. Здесь полнотекст
  бессилен по устройству, и именно ради них нужны вектора.

Разделение обязательно: без него непонятно, что именно чинить.
"""

import json
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from documents.models import Document  # noqa: E402
from documents.services.search_service import SearchService  # noqa: E402

#: Вопрос и **начало имени файла**, в котором лежит ответ.
#: Совпадение по началу имени, потому что имена содержат «(1)» и расширение.
QUESTIONS = [
    # --- дословные: слова вопроса есть в тексте ---
    ("конкатенация строк", "Строки", "literal"),
    ("лямбда-функции", "Продвинутые функции", "literal"),
    ("как объявить функцию def", "Базовые функции. Шпаргалка", "literal"),
    ("создание множества", "Множества", "literal"),
    ("перебор значений словаря", "Словари", "literal"),
    ("синтаксис цикла for in", "Циклы", "literal"),
    ("переменные типа bool", "Основы синтаксиса", "literal"),
    ("как определить длину строки", "Строки", "literal"),
    # --- перефразированные: слова другие, смысл тот же ---
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
    user = get_user_model().objects.filter(is_superuser=True).first()
    if user is None:
        user = get_user_model().objects.first()
    if user is None:
        print("нет ни одного пользователя — замер невозможен")
        return 2

    service = SearchService(user)
    # Результат поиска не несёт имени документа — только id. Достаём имена
    # одним запросом, а не по одному на каждый результат.
    titles_by_id = dict(Document.objects.values_list("id", "file_name"))
    rows = []

    for query, expected, kind in QUESTIONS:
        response = service.search(query, save_history=False, with_highlights=False)
        titles = [titles_by_id.get(result.id, f"неизвестный #{result.id}") for result in response.results[:TOP_K]]

        # Позиция правильного документа: 1..TOP_K, либо 0 — не найден.
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
                "found_total": response.total,
                "top": titles[:3],
            }
        )

    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
