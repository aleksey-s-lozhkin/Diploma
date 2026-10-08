"""Выпуск и отзыв токенов потребителей поиска.

Значение токена показывается один раз — при выпуске: в базе лежит только хеш,
и восстановить значение потом нельзя, можно лишь выпустить новый.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from documents.models import ApiToken

User = get_user_model()


class Command(BaseCommand):
    help = "Выпустить токен потребителя поиска (docs/SEARCH-CONTRACT.md, §2)"

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Кому выдан: semen, lapot, ...")
        parser.add_argument(
            "--scope",
            choices=[ApiToken.SCOPE_SERVICE, ApiToken.SCOPE_PERSONAL],
            default=ApiToken.SCOPE_SERVICE,
            help="service — только публичные документы, personal — документы человека",
        )
        parser.add_argument("--email", help="Пользователь для персонального токена")
        parser.add_argument("--list", action="store_true", help="Показать выпущенные токены")
        parser.add_argument("--revoke", type=int, metavar="ID", help="Отозвать токен по номеру")
        parser.add_argument(
            "--activate",
            type=int,
            metavar="ID",
            help="Вернуть отозванный токен в работу",
        )

    def handle(self, *args, **options):
        if options["list"]:
            return self._list()
        if options["revoke"]:
            return self._set_active(options["revoke"], False)
        if options["activate"]:
            return self._set_active(options["activate"], True)

        name = options["name"]
        if not name:
            raise CommandError("Укажите --name (или --list, --revoke ID, --activate ID)")

        user = None
        if options["scope"] == ApiToken.SCOPE_PERSONAL:
            email = options["email"]
            if not email:
                raise CommandError("Для персонального токена нужен --email")
            user = User.objects.filter(email=email).first()
            if user is None:
                raise CommandError(f"Пользователь {email} не найден")

        token, raw = ApiToken.issue(name=name, scope=options["scope"], user=user)
        self.stdout.write(self.style.SUCCESS(f"Токен #{token.pk} для «{token.name}» выпущен."))
        self.stdout.write(f"  область: {token.get_scope_display()}")
        if user is not None:
            self.stdout.write(f"  пользователь: {user.email}")
        self.stdout.write("")
        self.stdout.write("  Значение (показывается один раз):")
        self.stdout.write(f"  {raw}")
        self.stdout.write("")

    def _list(self):
        tokens = ApiToken.objects.select_related("user").all()
        if not tokens:
            self.stdout.write("Токенов нет.")
            return
        for token in tokens:
            state = "действует" if token.is_active else "отозван"
            used = token.last_used_at.strftime("%d.%m.%Y %H:%M") if token.last_used_at else "ни разу"
            user = token.user.email if token.user else "—"
            self.stdout.write(
                f"#{token.pk:<4} {token.prefix}…  {token.name:<20} {token.scope:<9} "
                f"пользователь: {user:<28} использован: {used:<16} {state}"
            )

    def _set_active(self, token_id, active):
        token = ApiToken.objects.filter(pk=token_id).first()
        if token is None:
            raise CommandError(f"Токен #{token_id} не найден")
        token.is_active = active
        token.save(update_fields=["is_active"])
        action = "возвращён в работу" if active else "отозван"
        self.stdout.write(self.style.SUCCESS(f"Токен #{token.pk} ({token.name}) {action}."))
