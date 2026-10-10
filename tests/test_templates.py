"""Шаблоны не должны показывать собственные комментарии.

`{# ... #}` в Django комментирует только до конца строки: многострочный
комментарий им не закрыть, и текст такого блока уезжает на страницу обычным
текстом. Ошибка тихая — её не видно ни в тестах, ни в консоли, только глазом в
браузере, поэтому проверка обходит все страницы, а не одну.
"""

import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from documents.models import Document, SearchHistory
from documents.services.search_service import SearchService

User = get_user_model()

#: Что ищем в готовой странице: и открытие, и закрытие комментария.
LEAKS = ("{#", "#}", "{% comment %}", "{% endcomment %}")


class NoTemplateCommentLeakTest(TestCase):
    def setUp(self):
        # Почта подтверждена: иначе страницы отвечают редиректом на проверку.
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.document = Document.objects.create(user=self.user, text="Договор поставки", rubrics=["право"])

    def assert_clean(self, response, where):
        self.assertEqual(response.status_code, 200, f"{where}: страница не открылась")
        body = response.content.decode()
        for leak in LEAKS:
            self.assertNotIn(leak, body, f"{where}: на страницу попал шаблонный комментарий {leak}")

    def test_anonymous_pages(self):
        for name in ("login", "register", "password_reset_request"):
            with self.subTest(name=name):
                self.assert_clean(self.client.get(reverse(name)), name)

    def test_authenticated_pages(self):
        self.client.force_login(self.user)
        for name in ("index", "dashboard", "document_create", "search_history"):
            with self.subTest(name=name):
                self.assert_clean(self.client.get(reverse(name)), name)

    def test_document_page(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("document_detail", args=[self.document.pk]))
        self.assert_clean(response, "document_detail")

    def test_change_password_page(self):
        self.client.force_login(self.user)
        self.assert_clean(self.client.get(reverse("change_password")), "change_password")

    def test_search_results_fragment(self):
        """Партиал подставляется в страницу отдельно — проверяем и его."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("search_results"), {"query": "договор"})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for leak in LEAKS:
            self.assertNotIn(leak, body, f"search_results: на страницу попал {leak}")


class BrandAndNavigationTest(TestCase):
    """Логотип, подвал и подписи в панели — часть интерфейса, а не украшение.

    Логотип уже пропадал при переделке оформления, и заметил это человек, а не
    проверка. Теперь на это есть тест.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )

    def test_dashboard_has_logo_footer_and_labelled_navigation(self):
        self.client.force_login(self.user)
        body = self.client.get(reverse("dashboard")).content.decode()

        # Имя и знак — то, по чему приложение узнаётся. Знак проверяем по
        # data-brand, а не по классу оформления: класс переименовывают при
        # первой же правке стилей, и тест на нём ломается на ровном месте,
        # ничего не сообщив о поломке. data-brand меняется только вместе с
        # именем приложения — то есть тогда, когда тест и должен упасть.
        self.assertIn("Сито", body, "имя приложения пропало из шапки")
        self.assertIn('data-brand="sito"', body, "знак пропал из шапки")
        self.assertIn('class="topbar"', body)
        self.assertIn('class="foot', body, "подвал пропал")
        for label in ("Поиск", "Документы", "Создать", "История", "Выйти"):
            self.assertIn(label, body, f"в панели переходов нет подписи «{label}»")

    def test_login_page_has_logo_and_footer(self):
        body = self.client.get(reverse("login")).content.decode()

        self.assertIn("Сито", body, "имя приложения пропало со страницы входа")
        self.assertIn('data-brand="sito"', body, "знак пропал со страницы входа")
        self.assertIn('class="foot', body)
        self.assertIn("Регистрация", body, "из подвала пропала ссылка на регистрацию")

    def test_dashboard_explains_itself(self):
        self.client.force_login(self.user)
        body = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Приватные документы видите только вы", body)


class StaticVersionTest(TestCase):
    """Ссылки на статику уходят с версией.

    Nginx отдаёт статику с кешем на месяц, а имя файла при выпуске не меняется:
    без версии в адресе человек после выкладки видел бы прежнее оформление.
    """

    def test_css_and_js_links_carry_version(self):
        body = self.client.get(reverse("login")).content.decode()

        self.assertRegex(body, r"css/app\.css\?v=\d+")
        self.assertRegex(body, r"js/htmx\.min\.js\?v=\d+")


class LayoutRegressionTest(TestCase):
    """Три поломки, которые нашлись на боевом глазами.

    Каждая тихая: страница отдаёт 200, тесты про содержимое проходят, а на
    экране — вторая шапка, подвал посреди страницы и непонятная кнопка темы.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_htmx_dashboard_returns_only_the_list(self):
        """Фильтры подменяют контейнер: в ответе не должно быть целой страницы."""
        response = self.client.get(reverse("dashboard"), {"show_public": "true"}, HTTP_HX_REQUEST="true")
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="dashboard-container"', body)
        # Подменяемый кусок — только список. Если в него попадёт шапка, знак
        # приедет вместе с ней и встанет посреди страницы. Ищем знак, а не
        # класс оформления, — по той же причине, что и в проверке выше.
        self.assertNotIn('data-brand="sito"', body, "в подменяемый кусок попала шапка со знаком")
        self.assertNotIn("<nav", body, "в подменяемый кусок попала панель переходов")
        self.assertNotIn("<footer", body, "в подменяемый кусок попал подвал")

    def test_htmx_dashboard_still_pushes_url(self):
        response = self.client.get(reverse("dashboard"), HTTP_HX_REQUEST="true")
        self.assertContains(response, 'hx-push-url="true"')

    def test_footer_sits_after_main(self):
        """Подвал вне main — иначе он не прижимается к низу окна."""
        body = self.client.get(reverse("index")).content.decode()

        self.assertLess(body.index("</main>"), body.index('class="foot'), "подвал остался внутри main")

    def test_theme_button_shows_current_mode(self):
        body = self.client.get(reverse("dashboard")).content.decode()

        for mode in ("only-auto", "only-light", "only-dark"):
            self.assertIn(mode, body, f"у кнопки темы нет варианта {mode}")
        for label in ("Авто", "Светлая", "Тёмная"):
            self.assertIn(label, body, f"режим темы не подписан: {label}")


class WideLayoutTest(TestCase):
    """Широкая раскладка: место на мониторе не должно пропадать.

    На телефоне всё в одну колонку, на мониторе — в две: форма рядом с
    результатом, списки карточками в несколько столбцов.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_search_page_stacks_form_and_results(self):
        body = self.client.get(reverse("index")).content.decode()

        self.assertIn('class="search-layout"', body)
        self.assertLess(
            body.index('class="search-layout"'),
            body.index('id="search-results"'),
            "результаты поиска должны идти после формы",
        )

    def test_auth_pages_explain_themselves(self):
        self.client.logout()
        for name in ("login", "register", "password_reset_request"):
            with self.subTest(name=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertIn('class="auth"', body)
                self.assertIn('class="auth-aside"', body)
                self.assertNotIn('class="card narrow"', body, "узкая карточка вернулась")

    def test_markup_stays_balanced(self):
        """Правки разметки делались строками — проверяем, что теги сошлись."""
        for name in ("index", "dashboard", "document_create", "search_history"):
            with self.subTest(name=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertEqual(
                    body.count("<div"),
                    body.count("</div>"),
                    f"{name}: число открытых и закрытых div разошлось",
                )


class AccessibilityTest(TestCase):
    """Контраст текста в светлой теме не ниже AA.

    Тёплый бежевый фон «съедает» контраст, и подписи на нём легко сделать
    нечитаемыми. Проверяем числом по WCAG, а не на глаз: 4.5:1 для обычного
    текста. Тёмная тема проверена вручную — там запас больше.
    """

    @staticmethod
    def _luminance(color):
        value = color.lstrip("#")
        channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def _ratio(self, first, second):
        a, b = self._luminance(first), self._luminance(second)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)

    def test_light_theme_text_passes_aa(self):
        css = (settings.BASE_DIR / "static_src" / "css" / "app.css").read_text()
        light = css[css.index(':root[data-theme="light"]') : css.index("* { box-sizing")]

        def value(name):
            match = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", light)
            self.assertIsNotNone(match, f"в светлой теме не найдена переменная --{name}")
            return match.group(1)

        background = value("bg")
        for name, label in (
            ("text", "основной текст"),
            ("text-soft", "мягкий текст"),
            ("text-muted", "приглушённый текст"),
            ("primary-hover", "ссылки"),
        ):
            ratio = self._ratio(value(name), background)
            self.assertGreaterEqual(round(ratio, 2), 4.5, f"{label} на фоне: {ratio:.2f}:1 — ниже AA")


class SearchFormTest(TestCase):
    """Поиск должен быть формой: иначе Enter работает по совпадению."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_search_is_a_real_form_with_submit_button(self):
        body = self.client.get(reverse("index")).content.decode()

        self.assertIn('id="search-form"', body)
        self.assertIn('type="submit"', body, "Enter не отправит запрос без submit-кнопки")
        self.assertIn('name="query"', body)
        self.assertIn('name="rubric"', body)
        self.assertIn('name="privacy"', body)

    def test_reset_button_is_hidden_until_something_is_chosen(self):
        body = self.client.get(reverse("index")).content.decode()
        self.assertIn('id="reset-button" hidden', body)

    def test_empty_query_returns_hint_not_error(self):
        response = self.client.post(reverse("search_results"), {"query": ""})
        self.assertEqual(response.status_code, 200)


class DashboardMetricsTest(TestCase):
    """Метрики дашборда говорят о документах, а не о размере страницы."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        Document.objects.create(user=self.user, text="Приватный", rubrics=["право"])
        Document.objects.create(user=self.user, text="Публичный", rubrics=["право"], is_public=True)
        self.client.force_login(self.user)

    def test_public_count_is_shown(self):
        body = self.client.get(reverse("dashboard")).content.decode()

        self.assertIn("публичных", body)
        self.assertNotIn("на этой странице", body)

    def test_toggle_is_a_segmented_control(self):
        body = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('class="segmented"', body)


class SearchResultCardTest(TestCase):
    """В результатах видно, из какого документа отрывок, и его можно скачать."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.document = Document.objects.create(
            user=self.user,
            text="Договор поставки",
            rubrics=["право"],
            file_name="Договор.pdf",
            summary="Шпаргалка про договоры.",
            keywords=["право"],
        )
        self.client.force_login(self.user)

    def test_card_shows_file_name_and_download(self):
        class FakeHit:
            def __init__(self, payload):
                self.payload = payload

            def to_dict(self):
                return dict(self.payload)

        class FakeResponse:
            total = 1
            page = 1
            total_pages = 1
            page_range = [1]
            results = [
                FakeHit(
                    {
                        "id": self.document.pk,
                        "rubrics": ["право"],
                        "text": "Договор поставки",
                        "created_date": self.document.created_date,
                        "is_public": False,
                        "highlights": ["Договор <mark>поставки</mark>"],
                    }
                )
            ]

        with mock.patch.object(SearchService, "search", return_value=FakeResponse()):
            response = self.client.post(reverse("search_results"), {"query": "поставки"})

        body = response.content.decode()
        self.assertIn("Договор.pdf", body, "в результатах не видно, из какого документа отрывок")
        self.assertIn("Шпаргалка про договоры", body, "в результатах нет описания документа")
        self.assertIn("<mark>поставки</mark>", body, "нет подсветки найденного слова")
        # Тело цикла результатов рисуется только при непустой выдаче, поэтому
        # проверять протечки надо здесь: на пустом ответе их не видно.
        for leak in ("{#", "#}"):
            self.assertNotIn(leak, body, f"в карточке результата виден шаблонный комментарий {leak}")


class HistoryDimmingTest(TestCase):
    """Запрос без результатов в истории бледнее: находки видны сразу."""

    def test_empty_result_row_is_dimmed(self):
        user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        SearchHistory.objects.create(user=user, query="нашлось", results_count=3)
        SearchHistory.objects.create(user=user, query="не нашлось", results_count=0)
        self.client.force_login(user)

        body = self.client.get(reverse("search_history")).content.decode()
        self.assertEqual(body.count("item dead"), 1, "пустой запрос не выделен")


class DocumentFormTest(TestCase):
    """Файл и ручной текст — одно поле смысла: при выбранном файле ввод убирается."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_form_has_dropzone(self):
        body = self.client.get(reverse("document_create")).content.decode()

        self.assertIn('class="dropzone"', body)
        self.assertIn('id="file-input"', body)
        self.assertIn('id="manual-text"', body)
        self.assertIn("Перетащите файл сюда", body)

    def test_drag_and_drop_is_wired(self):
        """Перетаскивание проверяем по коду: браузера в тестах нет."""
        body = self.client.get(reverse("document_create")).content.decode()

        self.assertIn("dragover", body)
        self.assertIn("DataTransfer", body, "файл из перетаскивания не попадёт в поле")
        self.assertIn('id="clear-file"', body)

    def test_old_warning_about_lost_text_is_gone(self):
        body = self.client.get(reverse("document_create")).content.decode()
        self.assertNotIn("вручную введённое не сохранится", body)


class SearchHintsTest(TestCase):
    """Пустое состояние поиска подсказывает рубрики — свои, не выдуманные."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_chips_come_from_the_users_own_rubrics(self):
        Document.objects.create(user=self.user, text="Договор", rubrics=["право", "договоры"])

        body = self.client.get(reverse("index")).content.decode()

        self.assertIn('data-rubric="право"', body)
        self.assertIn('data-rubric="договоры"', body)

    def test_no_chips_without_rubrics(self):
        Document.objects.create(user=self.user, text="Без рубрик", rubrics=[])

        body = self.client.get(reverse("index")).content.decode()

        # Проверяем именно разметку подсказок: строка «data-rubric» есть и в
        # скрипте-обработчике, который остаётся на странице всегда.
        self.assertNotIn('class="chip"', body)
        self.assertNotIn("Или начните с рубрики", body)


class HistoryGroupingTest(TestCase):
    """История читается лентой по дням, а не сотней одинаковых карточек."""

    def test_entries_are_grouped_by_day(self):
        user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        long_ago = SearchHistory.objects.create(user=user, query="давний", results_count=1)
        SearchHistory.objects.filter(pk=long_ago.pk).update(created_at=timezone.now() - timedelta(days=10))
        yesterday = SearchHistory.objects.create(user=user, query="вчерашний", results_count=1)
        SearchHistory.objects.filter(pk=yesterday.pk).update(created_at=timezone.now() - timedelta(days=1))
        SearchHistory.objects.create(user=user, query="сегодняшний", results_count=2)
        self.client.force_login(user)

        body = self.client.get(reverse("search_history")).content.decode()

        self.assertIn("Сегодня", body)
        self.assertIn("Вчера", body)
        self.assertRegex(body, r"\d{2}\.\d{2}\.\d{4}", "у старых записей нет даты")
        self.assertEqual(body.count('class="day"'), 3, "записей трёх дней, а заголовков не три")


class SearchStateInUrlTest(TestCase):
    """Возврат по «назад» должен показывать прежние результаты.

    Состояние поиска живёт в адресе: иначе браузер открывает главную без
    запроса, и поиск приходится повторять руками.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="pass12345", is_active=True, is_email_verified=True
        )
        self.client.force_login(self.user)

    def test_state_is_kept_in_the_address(self):
        body = self.client.get(reverse("index")).content.decode()

        self.assertIn("history.pushState", body, "адрес не обновляется — «назад» не вернёт результаты")
        self.assertIn("history.replaceState", body)
        self.assertIn("popstate", body, "переходы назад/вперёд не обрабатываются")
        self.assertIn("htmx.trigger(form, 'submit')", body)
        self.assertIn("location.search", body, "запрос из адреса не восстанавливается")

    def test_reset_returns_to_clean_address(self):
        body = self.client.get(reverse("index")).content.decode()
        self.assertIn("history.pushState(null, '', location.pathname)", body)
