import logging
import time
from dataclasses import dataclass
from typing import Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Результат проверки rate limit"""

    allowed: bool
    remaining: int
    retry_after: int
    limit: int
    period: int

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "retry_after": self.retry_after,
            "limit": self.limit,
            "period": self.period,
        }


class RateLimiter:
    """Rate limiter с использованием Django cache (Redis)"""

    def __init__(self, prefix: str, limit: int = 60, period: int = 60):
        self.prefix = prefix
        self.limit = limit
        self.period = period
        self._cache_key_template = f"rl:{prefix}:{{key}}"

    def _get_cache_key(self, key: str) -> str:
        return self._cache_key_template.format(key=key)

    def check(self, key: str) -> Tuple[bool, int, int]:
        """Проверить rate limit для ключа"""

        cache_key = self._get_cache_key(key)
        now = time.time()

        data = cache.get(cache_key)

        if data is None:
            cache.set(cache_key, {"count": 1, "window_start": now}, timeout=self.period)
            logger.debug(f"[RL:{self.prefix}] First request for {key}")
            return True, self.limit - 1, 0

        if now - data["window_start"] > self.period:
            cache.set(cache_key, {"count": 1, "window_start": now}, timeout=self.period)
            logger.debug(f"[RL:{self.prefix}] Window expired for {key}")
            return True, self.limit - 1, 0

        data["count"] += 1
        logger.debug(f"[RL:{self.prefix}] {key}: count={data['count']}, limit={self.limit}")

        if data["count"] > self.limit:
            retry_after = int(self.period - (now - data["window_start"]))
            logger.warning(f"[RL:{self.prefix}] LIMIT EXCEEDED for {key}, retry_after={retry_after}")
            return False, 0, retry_after

        cache.set(cache_key, data, timeout=self.period)
        remaining = self.limit - data["count"]

        return True, remaining, 0

    def check_with_result(self, key: str) -> RateLimitResult:
        """Вернуть результат в виде объекта"""
        allowed, remaining, retry_after = self.check(key)
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            retry_after=retry_after,
            limit=self.limit,
            period=self.period,
        )

    def reset(self, key: str) -> None:
        """Сбросить лимит для ключа"""
        cache_key = self._get_cache_key(key)
        cache.delete(cache_key)
        logger.info(f"[RL:{self.prefix}] Reset for {key}")

    def get_current_count(self, key: str) -> int:
        """Получить текущее количество запросов"""
        cache_key = self._get_cache_key(key)
        data = cache.get(cache_key)
        return data["count"] if data else 0


class RateLimiters:
    """Предустановленные лимитеры"""

    @staticmethod
    def register() -> RateLimiter:
        """Регистрация: 3 попытки в час на email"""
        return RateLimiter("register", limit=3, period=3600)

    @staticmethod
    def login() -> RateLimiter:
        """Логин: 10 попыток в 5 минут на email"""
        return RateLimiter("login", limit=10, period=300)

    @staticmethod
    def password_reset() -> RateLimiter:
        """Сброс пароля: 3 попытки в час на email"""
        return RateLimiter("password_reset", limit=3, period=3600)

    @staticmethod
    def api_search() -> RateLimiter:
        """API поиск: 30 запросов в минуту на пользователя"""
        return RateLimiter("api_search", limit=30, period=60)

    @staticmethod
    def api_general() -> RateLimiter:
        """Общий API: 100 запросов в минуту на пользователя"""
        return RateLimiter("api_general", limit=100, period=60)
