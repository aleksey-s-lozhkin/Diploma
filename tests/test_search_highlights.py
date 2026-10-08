"""Подсветка результатов поиска: разметка остаётся, чужой HTML — нет.

Фрагменты подсветки собирает Elasticsearch из текста документа, а текст пишет
пользователь. Шаблон выводит их готовой разметкой, поэтому до правки документ
со <script> выполнялся бы в браузере того, кто ищет.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from elasticsearch_dsl import Search
from elasticsearch_dsl.utils import AttrDict

from documents.services.search_service import HIGHLIGHT_POST_TAG, HIGHLIGHT_PRE_TAG, SearchService, sanitize_highlight

User = get_user_model()


class FakeMeta:
    """Повторяет поведение ответа Elasticsearch: доступ и по ключу, и по атрибуту."""

    def __init__(self, fragments):
        self.highlight = AttrDict({"text": fragments})


class FakeHit:
    def __init__(self, fragments):
        self.meta = FakeMeta(fragments)


class HighlightSanitizingTest(TestCase):
    def test_script_is_escaped(self):
        result = sanitize_highlight("<script>alert(1)</script> python")

        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_own_highlight_tags_survive(self):
        result = sanitize_highlight(f"python {HIGHLIGHT_PRE_TAG}django{HIGHLIGHT_POST_TAG}")

        self.assertIn(HIGHLIGHT_PRE_TAG, result)
        self.assertIn(HIGHLIGHT_POST_TAG, result)

    def test_attributes_with_handlers_are_escaped(self):
        result = sanitize_highlight('<img src=x onerror="alert(1)">')

        self.assertNotIn('onerror="alert', result)
        self.assertIn("&lt;img", result)

    def test_extract_highlights_sanitizes_document_text(self):
        hit = FakeHit(["<script>alert(1)</script> python <script>alert(2)</script>"])

        fragments = SearchService.extract_highlights(hit)

        self.assertEqual(len(fragments), 1)
        self.assertNotIn("<script>", fragments[0])

    def test_empty_fragments_are_skipped(self):
        self.assertEqual(SearchService.extract_highlights(FakeHit(["   ", ""])), [])


class HighlightQueryTest(TestCase):
    """Запрос просит Elasticsearch размечать подсветку нашими тегами."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="highlight@example.com", password="pass12345", is_active=True, is_email_verified=True
        )

    def _capture_body(self):
        captured = {}

        class EmptyResponse:
            class hits:
                class total:
                    value = 0

            def __iter__(self):
                return iter([])

        def fake_execute(search_self):
            captured["body"] = search_self.to_dict()
            return EmptyResponse()

        with mock.patch.object(Search, "execute", new=fake_execute):
            SearchService(self.user).search(query="python", save_history=False, with_highlights=True)
        return captured["body"]

    def test_highlight_uses_own_tags(self):
        highlight = self._capture_body()["highlight"]

        self.assertEqual(highlight["pre_tags"], [HIGHLIGHT_PRE_TAG])
        self.assertEqual(highlight["post_tags"], [HIGHLIGHT_POST_TAG])
        self.assertIn("text", highlight["fields"])
