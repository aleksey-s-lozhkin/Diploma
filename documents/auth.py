"""Аутентификация потребителей поиска по токену.

Контракт (docs/SEARCH-CONTRACT.md, §2) требует, чтобы потребитель
представлялся токеном, а не идентификатором пользователя в запросе: ошибка в
любом потребителе иначе открывала бы чужие документы — достаточно подставить
число. Здесь токен превращается в «кто спрашивает»: персональный — в человека,
служебный — в отсутствие человека при видимости только публичных документов.
"""

import logging

from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import permissions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import ApiToken

logger = logging.getLogger(__name__)

#: Обновляем отметку последнего использования не чаще, чем раз в этот интервал:
#: запись в базу на каждый поисковый запрос не нужна.
LAST_USED_INTERVAL = timezone.timedelta(minutes=5)


class ApiTokenAuthentication(BaseAuthentication):
    """Заголовок `Authorization: Bearer <токен потребителя>`."""

    keyword = b"bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None  # не наш способ — пусть попробуют остальные
        if header[0].lower() != self.keyword:
            raise AuthenticationFailed("Ожидается заголовок Authorization: Bearer <токен>")
        if len(header) != 2:
            raise AuthenticationFailed("В заголовке Authorization должен быть один токен")

        try:
            raw = header[1].decode("utf-8")
        except UnicodeDecodeError:
            raise AuthenticationFailed("Токен должен быть текстом") from None

        token = (
            ApiToken.objects.select_related("user").filter(key_hash=ApiToken.hash_value(raw), is_active=True).first()
        )
        if token is None:
            raise AuthenticationFailed("Токен недействителен")

        self._touch(token)
        # Служебному токену человека нет: видимость задаёт сам токен, а не
        # пользователь, поэтому request.user остаётся анонимным.
        return (token.user, token)

    @staticmethod
    def _touch(token):
        now = timezone.now()
        if token.last_used_at and now - token.last_used_at < LAST_USED_INTERVAL:
            return
        try:
            ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
        except Exception:
            # Отметка — удобство для администратора, а не условие поиска.
            logger.warning("Не удалось обновить last_used_at токена %s", token.pk, exc_info=True)

    def authenticate_header(self, request):
        return "Bearer"


class HasApiToken(permissions.BasePermission):
    """Пускает только запросы с действующим токеном потребителя."""

    message = "Нужен токен потребителя поиска"

    def has_permission(self, request, view):
        return isinstance(request.auth, ApiToken)


class ApiTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    """Описание токена потребителя для схемы API.

    Без этого расширения drf-spectacular не знает, как показать способ
    аутентификации, и в описании появляется предупреждение вместо схемы.
    """

    target_class = "documents.auth.ApiTokenAuthentication"
    name = "ApiToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "ds_s_… (служебный) или ds_p_… (персональный)",
            "description": "Токен потребителя поиска: кого искать, решает он, а не запрос",
        }
