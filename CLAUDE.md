# Память проекта DocSearch

Файл читается в начале каждой сессии. Здесь только то, что нельзя вывести из
кода: правила работы, окружение и грабли, которые уже стоили времени.
Состояние (что сделано, что в работе) — в [docs/STATUS.md](docs/STATUS.md).

> **Одно из трёх связанных приложений.** Рядом — лапоть (главное) и Самогон (чат).
> У всех **одна видеокарта, одна модель `qwen3:8b`, один сервер и один реестр
> образов**, поэтому они мешают друг другу, хотя лежат в разных репозиториях.
>
> **Картина целиком и договор о работе — в
> [`lapot/docs/PROJECTS.md`](../lapot/docs/PROJECTS.md).** Читать перед
> работой, которая задевает соседей: сменой модели, настройками Ollama,
> поиском, деплоем, инфраструктурой.
>
> Правило: **решение живёт в том репозитории, где его исполняют** — и попадает
> в этот документ ссылкой.

## Что за проект

Поиск по документам: Django + DRF + Elasticsearch + HTMX. Английский язык
интерфейса не нужен, весь текст — русский. Дипломный проект, но эксплуатируется
по-настоящему: боевой домен `docsearch.pyconstrictor.ru`.

## Проверки

```bash
pytest                      # весь набор, включая documents/tests — не сужать до tests/
pytest tests/ -q            # так теряются 19 тестов нарезки (они в documents/tests)
black --line-length 120 . && isort --profile black --line-length 120 . && flake8 .
pre-commit run --all-files  # PRE_COMMIT_HOME=/tmp/dsh-precommit, если домашний каталог недоступен
manage.py spectacular --file docs/api/openapi.json --format openapi-json   # схема проверяется в CI
```

## Как смотреть интерфейс своими глазами

В системе есть Android Studio и AVD — скриншоты у людей просить не нужно.

```bash
export ANDROID_HOME=~/Library/Android/sdk
$ANDROID_HOME/emulator/emulator -avd Pixel_9 -no-window -no-audio -gpu swiftshader_indirect &
$ANDROID_HOME/platform-tools/adb wait-for-device
$ANDROID_HOME/platform-tools/adb shell am start -a android.intent.action.VIEW -d "https://docsearch.pyconstrictor.ru/login/"
$ANDROID_HOME/platform-tools/adb exec-out screencap -p > /tmp/shot.png
```

Вход под тестовым пользователем: `adb shell input tap <x> <y>`, затем
`adb shell input text ...`. Широкий экран (десктопная раскладка от 860 px) —
`adb shell wm size 1600x1000`. Остановить эмулятор: `adb emu kill`.

## Правила, которые уже нарушались и стоили времени

- **`{# … #}` в Django комментирует только до конца строки.** Многострочный
  комментарий выводится на страницу текстом. Только `{% comment %} … {% endcomment %}`.
  Есть тест-сторож, но он проверяет лишь то, что реально отрисовалось: тело цикла
  с пустой выдачей он не видит — проверять надо и с непустой.
- **Читать настройки через `getattr(settings, ...)`.** `config/settings_ci.py` —
  самостоятельный модуль со своим списком, и отсутствующая переменная роняет
  страницу (спотыкались дважды: `STATIC_VERSION`, `SUMMARY_TEXT_LIMIT`).
- **htmx-запрос должен получать партиал, а не целую страницу.** Иначе страница
  вкладывается в свой же контейнер: вторые шапка, логотип и подвал.
- **Сохранение документа не зависит от Elasticsearch и языковой модели.** Всё
  внешнее — best-effort в `transaction.on_commit`, ошибки только в журнал.
- **`/health/` и `/health/ready/` вне `SECURE_SSL_REDIRECT`** — иначе healthcheck
  контейнера ломается на редиректе.
- **Данные прода не менять.** При проверках создавать своих пользователей и свои
  документы. Один раз я включил публичность всем документам владельца, чтобы
  увидеть карточки анонимом — так делать нельзя.
- **Документация обновляется вместе с кодом.** Устаревший документ хуже
  отсутствующего: он врёт с уверенностью.

## Git и выкладка

- Ветки: `feature/*` → `develop`, релиз `develop` → `main`, hotfix от `main`.
  Мерж в `main` сам запускает публикацию образа и деплой по SHA.
- После релиза `main` вливается обратно в `develop`.
- Деплой: образ в Docker Hub, выкладка по SSH, health-gate, дамп перед миграциями.
  Подробности — [docs/DEPLOY.md](docs/DEPLOY.md).
- Падение публикации из-за Docker Hub (500, таймаут `auth.docker.io`) — это их
  авария, а не наш код: выкладку достаточно перезапустить.

## Окружение (без секретов)

- Хост `infra-dev` (SSH, порт 2222, пользователь `alserloz`); общие контейнеры
  `postgres`, `redis`, `elasticsearch`, `nginx`; проект — `/srv/compose/diploma`,
  окружение — `/srv/config/env/diploma.env` (права 600), медиа — `/srv/data/diploma`.
- Индексы: `documents` (целые документы) и `chunks` (отрывки для контракта).
  Пересборка: `manage.py search_index --rebuild -f`, `manage.py reextract_text`,
  `manage.py reindex_chunks`.
- Языковая модель: Ollama в локальной сети, `OLLAMA_URL` в окружении.
  Описания, теги и дословный отрывок — **`qwen3:8b`**, общая с лаптем и
  Самогоном ([ADR-0010](https://github.com/aleksey-s-lozhkin/lapot/blob/main/docs/decisions/0010-one-model-for-two-apps.md))
  (на замере быстрее и точнее). Ответ модели принимается только если он дословно
  есть в тексте документа.
- Граница с потребителями зафиксирована в [docs/SEARCH-CONTRACT.md](docs/SEARCH-CONTRACT.md):
  `POST /api/v1/search/retrieve`, кого искать решает токен (не запрос).
