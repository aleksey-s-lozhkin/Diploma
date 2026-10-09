"""Шаблоны не должны показывать собственные комментарии.

`{# ... #}` в Django комментирует только до конца строки: многострочный
комментарий им не закрыть, и текст такого блока уезжает на страницу обычным
текстом. Ошибка тихая — её не видно ни в тестах, ни в консоли, только глазом в
браузере, поэтому проверка обходит все страницы, а не одну.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from documents.models import Document

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

        self.assertIn("logo.jpeg", body, "логотип пропал из шапки")
        self.assertIn('class="topbar"', body)
        self.assertIn('class="foot', body, "подвал пропал")
        for label in ("Поиск", "Документы", "Создать", "История", "Выйти"):
            self.assertIn(label, body, f"в панели переходов нет подписи «{label}»")

    def test_login_page_has_logo_and_footer(self):
        body = self.client.get(reverse("login")).content.decode()

        self.assertIn("logo.jpeg", body)
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
        self.assertNotIn("logo.jpeg", body, "в подменяемый кусок попала шапка с логотипом")
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

    def test_search_page_has_two_columns(self):
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
