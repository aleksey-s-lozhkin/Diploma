"""Описания и теги документов от языковой модели.

Модель может быть недоступна — это нормальный случай, а не ошибка: документ
должен сохраняться, а поиск работать.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from documents.models import Document
from documents.services import summary_service

User = get_user_model()
LONG_TEXT = "Пишем про словари и множества в python. " * 20


class SummaryServiceTest(TestCase):
    @override_settings(OLLAMA_URL="")
    def test_disabled_without_url(self):
        self.assertFalse(summary_service.is_enabled())
        self.assertEqual(summary_service.summarize_text(LONG_TEXT), ("", []))

    @override_settings(OLLAMA_URL="http://model.local")
    def test_json_is_extracted_from_model_answer(self):
        answer = 'Готово: {"summary": "Про словари", "keywords": ["#python", "dict", ""]}'
        with mock.patch.object(summary_service, "_ask_model", return_value=answer):
            summary, keywords = summary_service.summarize_text(LONG_TEXT)

        self.assertEqual(summary, "Про словари")
        self.assertEqual(keywords, ["python", "dict"], "решётка и пустые теги должны убираться")

    @override_settings(OLLAMA_URL="http://model.local")
    def test_model_failure_returns_nothing(self):
        with mock.patch.object(summary_service, "_ask_model", side_effect=OSError("нет связи")):
            self.assertEqual(summary_service.summarize_text(LONG_TEXT), ("", []))

    @override_settings(OLLAMA_URL="http://model.local")
    def test_short_text_is_not_sent_to_model(self):
        with mock.patch.object(summary_service, "_ask_model") as ask:
            self.assertEqual(summary_service.summarize_text("мало текста"), ("", []))
        ask.assert_not_called()

    @override_settings(OLLAMA_URL="http://model.local")
    def test_document_gets_summary_and_tags(self):
        user = User.objects.create_user(email="owner@example.com", password="pass12345")
        document = Document.objects.create(user=user, text=LONG_TEXT)

        with mock.patch.object(
            summary_service, "_ask_model", return_value='{"summary": "О словарях", "keywords": ["python", "dict"]}'
        ):
            self.assertTrue(summary_service.summarize_document(document))

        document.refresh_from_db()
        self.assertEqual(document.summary, "О словарях")
        self.assertEqual(document.keywords, ["python", "dict"])

    @override_settings(OLLAMA_URL="")
    def test_command_says_model_is_not_configured(self):
        call_command("summarize_documents")  # не должно быть исключения


class SummaryInUiTest(TestCase):
    """В карточке видно описание и теги, а не обрывок текста."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_card_shows_summary_and_tags(self):
        Document.objects.create(
            user=self.user,
            text=LONG_TEXT,
            file_name="Словари.pdf",
            summary="Шпаргалка по словарям и множествам в python.",
            keywords=["python", "dict"],
        )

        body = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn("Шпаргалка по словарям", body)
        self.assertIn("#python", body)
        self.assertIn("#dict", body)

    def test_without_summary_card_falls_back_to_text(self):
        Document.objects.create(user=self.user, text=LONG_TEXT)

        body = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn("Пишем про словари", body, "без описания в карточке должен быть текст")


class TestOneSharedModel:
    """Все запросы к модели идут на **одну** модель.

    На видеокарте 8 ГБ две модели не помещаются:

        qwen3:8b при ctx 8192   6,19 ГБ
        qwen3:4b-instruct       3,18 ГБ в видеопамяти

    Загружая меньшую, сервис вытесняет общую — и следующий гость Самогона
    или человек в лапте ждёт двадцать секунд загрузки. Замер показывал,
    что меньшая модель на отрывке быстрее и точнее, но вытеснения в том
    замере не было, а цена его больше выигрыша: отрывок кешируется на
    сутки, а вытеснение бьёт по каждому обращению.

    Условие записано в lapot/docs/decisions/0010.
    """

    def test_fragment_uses_the_shared_model(self):
        from documents.services.summary_service import DEFAULT_FRAGMENT_MODEL, DEFAULT_MODEL

        assert (
            DEFAULT_FRAGMENT_MODEL == DEFAULT_MODEL
        ), "отрывок ходит в свою модель — это вытеснит общую с лаптем и Самогоном"

    def test_shared_model_is_qwen3_8b(self):
        from documents.services.summary_service import DEFAULT_MODEL

        assert DEFAULT_MODEL == "qwen3:8b"
