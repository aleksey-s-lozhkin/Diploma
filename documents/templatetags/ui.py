"""Теги оформления: иконки и переключатель темы.

Иконки нарисованы здесь, а не подключены набором: пока их два десятка,
отдельная зависимость и сборка ради них не окупаются, а SVG в разметке
наследует цвет текста и не мигает при загрузке. Стиль тот же, что у lapot:
24×24, линия 1.7, скруглённые концы — линия читается на любом фоне.
Смысл задаёт aria-label на кнопке, сама иконка для чтения с экрана скрыта.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Контуры иконок. Ключ — имя, значение — разметка внутри <svg>.
ICONS = {
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M15.8 15.8 20 20"/>',
    "docs": (
        '<path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>'
        '<path d="M14 3v4h4"/><path d="M9 12h6"/><path d="M9 16h6"/>'
    ),
    "file": ('<path d="M7 3h7l4 4v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>' '<path d="M14 3v4h4"/>'),
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "logout": '<path d="M15 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h9"/><path d="M12 12h8"/><path d="M17 9l3 3-3 3"/>',
    "upload": '<path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/><path d="M12 16V4"/><path d="M8 8l4-4 4 4"/>',
    "download": '<path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/><path d="M12 4v12"/><path d="M8 12l4 4 4-4"/>',
    "eye": '<path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
    "trash": (
        '<path d="M4 7h16"/><path d="M9 7V5h6v2"/>'
        '<path d="M6 7l1 12h10l1-12"/><path d="M10 11v5"/><path d="M14 11v5"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/>'
        '<path d="M12 3.5c2.5 2.4 2.5 14.6 0 17-2.5-2.4-2.5-14.6 0-17z"/>'
    ),
    "lock": '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "close": '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
    "alert": '<path d="M12 4.5 21 19.5H3z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    "back": '<path d="M11 6l-6 6 6 6"/><path d="M5 12h14"/>',
    "chevron-left": '<path d="M14 6l-6 6 6 6"/>',
    "chevron-right": '<path d="M10 6l6 6-6 6"/>',
    "tag": '<path d="M11 3.5H5.5A1.5 1.5 0 0 0 4 5v5.5l9.5 9.5a1.5 1.5 0 0 0 2.1 0l4.4-4.4a1.5 1.5 0 0 0 0-2.1z"/><path d="M8 8h.01"/>',
    "user": '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6"/>',
    "theme": '<circle cx="12" cy="12" r="4"/><path d="M12 3v1.5"/><path d="M12 19.5V21"/><path d="M3 12h1.5"/><path d="M19.5 12H21"/><path d="M5.6 5.6l1 1"/><path d="M17.4 17.4l1 1"/><path d="M18.4 5.6l-1 1"/><path d="M6.6 17.4l-1 1"/>',
}


@register.simple_tag
def icon(name: str, size: int = 20) -> str:
    """Иконка интерфейса. Неизвестное имя — пустая строка, а не исключение:
    опечатка в шаблоне не должна ронять страницу целиком."""
    body = ICONS.get(name)
    if not body:
        return ""
    return format_html(
        '<svg class="icon" width="{}" height="{}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        size,
        size,
        # Разметка иконок — свои константы, экранировать её не нужно; всё
        # остальное format_html экранирует сам.
        mark_safe(body),
    )
