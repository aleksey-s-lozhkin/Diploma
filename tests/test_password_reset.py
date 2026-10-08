"""Сброс пароля: одинаковый ответ для любого адреса и экранирование в письмах."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from users.email_utils import send_password_reset_email, send_verification_email

User = get_user_model()


class PasswordResetEnumerationTest(TestCase):
    """Ответ на запрос сброса не зависит от того, есть ли такой адрес."""

    def setUp(self):
        self.url = reverse("password_reset_request")
        self.user = User.objects.create_user(
            email="known@example.com", password="pass12345", is_active=True, is_email_verified=True
        )

    def test_existing_email_gets_letter(self):
        response = self.client.post(self.url, {"email": "known@example.com"})

        self.assertRedirects(response, "/login/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("known@example.com", mail.outbox[0].to)

    def test_unknown_email_gets_same_answer_without_letter(self):
        response = self.client.post(self.url, {"email": "nobody@example.com"})

        # Тот же редирект и то же сообщение, что и для существующего адреса.
        self.assertRedirects(response, "/login/")
        self.assertEqual(len(mail.outbox), 0)


class EmailEscapingTest(TestCase):
    """Имя пользователя попадает в HTML письма, значит его нужно экранировать."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="xss@example.com",
            password="pass12345",
            first_name="<img src=x onerror=alert(1)>",
            is_active=True,
            is_email_verified=True,
        )
        self.request = self.client.request().wsgi_request

    def test_verification_email_escapes_name(self):
        send_verification_email(self.user, self.request)
        html = mail.outbox[-1].alternatives[0][0]

        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)

    def test_reset_email_escapes_name(self):
        send_password_reset_email(self.user, self.request)
        html = mail.outbox[-1].alternatives[0][0]

        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)
