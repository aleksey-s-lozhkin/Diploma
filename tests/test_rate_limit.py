from django.core.cache import cache
from django.test import TestCase

from documents.rate_limit import RateLimiter, RateLimiters


class RateLimiterLogicTest(TestCase):
    """Тесты логики работы одного RateLimiter"""

    def setUp(self):
        cache.clear()
        self.limiter = RateLimiter(prefix="test", limit=3, period=60)

    def test_first_request_allowed(self):
        """Первый запрос разрешён"""
        allowed, remaining, _ = self.limiter.check("test_key")
        self.assertTrue(allowed)
        self.assertEqual(remaining, 2)

    def test_requests_within_limit(self):
        """Запросы в пределах лимита"""
        for _ in range(3):
            allowed, _, _ = self.limiter.check("test_key")
            self.assertTrue(allowed)

    def test_exceed_limit(self):
        """Превышение лимита"""
        for _ in range(4):
            allowed, _, _ = self.limiter.check("test_key")
        self.assertFalse(allowed)

    def test_reset_limit(self):
        """Сброс лимита"""
        self.limiter.check("test_key")
        self.limiter.reset("test_key")
        allowed, remaining, _ = self.limiter.check("test_key")
        self.assertTrue(allowed)
        self.assertEqual(remaining, 2)


class RateLimitersPresetsTest(TestCase):
    """Тесты предустановленных лимитеров из класса RateLimiters"""

    def test_register_limiter(self):
        """Лимитер регистрации: 3 попытки в час"""
        limiter = RateLimiters.register()
        self.assertEqual(limiter.limit, 3)
        self.assertEqual(limiter.period, 3600)
        self.assertEqual(limiter.prefix, "register")

    def test_login_limiter(self):
        """Лимитер логина: 10 попыток в 5 минут"""
        limiter = RateLimiters.login()
        self.assertEqual(limiter.limit, 10)
        self.assertEqual(limiter.period, 300)
        self.assertEqual(limiter.prefix, "login")

    def test_password_reset_limiter(self):
        """Лимитер сброса пароля: 3 попытки в час"""
        limiter = RateLimiters.password_reset()
        self.assertEqual(limiter.limit, 3)
        self.assertEqual(limiter.period, 3600)
        self.assertEqual(limiter.prefix, "password_reset")

    def test_api_search_limiter(self):
        """Лимитер API поиска: 30 запросов в минуту"""
        limiter = RateLimiters.api_search()
        self.assertEqual(limiter.limit, 30)
        self.assertEqual(limiter.period, 60)
        self.assertEqual(limiter.prefix, "api_search")

    def test_api_general_limiter(self):
        """Общий API лимитер: 100 запросов в минуту"""
        limiter = RateLimiters.api_general()
        self.assertEqual(limiter.limit, 100)
        self.assertEqual(limiter.period, 60)
        self.assertEqual(limiter.prefix, "api_general")
