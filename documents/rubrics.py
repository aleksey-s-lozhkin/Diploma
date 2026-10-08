"""Список рубрик пользователя и его кэш.

Список рубрик собирается по своим и публичным документам и показывается в форме
создания и в подсказках. Раньше страница с этим списком кэшировалась целиком
через cache_page без vary_on_cookie: один пользователь получал HTML, собранный
для другого, вместе с чужими названиями рубрик.

Здесь кэшируется только сам список, под ключом владельца, и ключ явный — его
можно удалить на любом бэкенде, в отличие от delete_pattern, который есть
только у Redis.
"""

import logging

from django.core.cache import cache
from django.db.models import Q

from documents.models import Document

logger = logging.getLogger(__name__)

# Небольшой TTL: чужие публичные документы меняют список, а сбрасываем мы
# только ключ владельца.
RUBRICS_CACHE_SECONDS = 300


def rubrics_cache_key(user_id) -> str:
    return f"rubrics_user_{user_id}"


def collect_rubrics(user) -> list:
    """Возвращает отсортированный список рубрик, доступных пользователю."""
    values = Document.objects.filter(Q(user=user) | Q(is_public=True)).values_list("rubrics", flat=True)

    unique_rubrics = set()
    for rubrics_list in values:
        # rubrics — JSONField: там может оказаться не список (правка через
        # админку), и обход падал бы с TypeError.
        for rubric in rubrics_list or []:
            unique_rubrics.add(rubric)

    return sorted(unique_rubrics)


def get_cached_rubrics(user) -> list:
    """Список рубрик из кэша, при промахе — из базы."""
    key = rubrics_cache_key(user.id)
    rubrics = cache.get(key)
    if rubrics is None:
        rubrics = collect_rubrics(user)
        try:
            cache.set(key, rubrics, timeout=RUBRICS_CACHE_SECONDS)
        except Exception:
            logger.warning("Не удалось закэшировать рубрики пользователя %s", user.id, exc_info=True)
    return rubrics


def invalidate_rubrics_cache(user_id):
    """Сбрасывает список рубрик владельца после изменения его документов."""
    try:
        cache.delete(rubrics_cache_key(user_id))
    except Exception:
        logger.warning("Не удалось сбросить кэш рубрик пользователя %s", user_id, exc_info=True)
