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
        self.assertIn('class="foot"', body, "подвал пропал")
        for label in ("Поиск", "Документы", "Создать", "История", "Выйти"):
            self.assertIn(label, body, f"в панели переходов нет подписи «{label}»")

    def test_login_page_has_logo_and_footer(self):
        body = self.client.get(reverse("login")).content.decode()

        self.assertIn("logo.jpeg", body)
        self.assertIn('class="foot"', body)
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
