"""Значения, нужные всем шаблонам."""

import os
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def static_version() -> str:
    """Версия статики для ссылок на css и js.

    Nginx отдаёт статику с кешем на месяц, а имя файла при выпуске не меняется:
    без версии в адресе человек после выкладки видел бы прежнее оформление и не
    понял бы, почему. Версия — время сборки образа, то есть новая выкладка даёт
    новое значение без ручных правок.

    Считается здесь, а не в настройках: набор настроек зависит от окружения
    (в проверках он свой), и значение не должно от этого пропадать.
    """
    newest = 0.0
    folders = [os.path.join(str(settings.BASE_DIR), "static_src")]
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        folders.append(str(static_root))

    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    continue

    # Пустая версия ломала бы сброс кеша, поэтому единица на крайний случай.
    return str(int(newest)) if newest else "1"


def asset_version(request) -> dict:
    """Версия статики в контексте шаблонов."""
    return {"asset_version": static_version()}
