# DocSearch — поиск по документам

[![CI](https://github.com/aleksey-s-lozhkin/Diploma/actions/workflows/ci.yml/badge.svg)](https://github.com/aleksey-s-lozhkin/Diploma/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-6.0-green.svg)](https://www.djangoproject.com/)
[![Elasticsearch](https://img.shields.io/badge/elasticsearch-8.11-blue.svg)](https://www.elastic.co/)

Сервис загрузки и полнотекстового поиска по документам: пользователь загружает
PDF, DOCX, XLSX или TXT либо вводит текст руками, система извлекает содержимое,
индексирует его в Elasticsearch и ищет с русской и английской морфологией.

Продакшен: **https://docsearch.pyconstrictor.ru** (хост `infra-dev`).

## Что умеет

- Загрузка файлов PDF, DOCX, XLSX, TXT с извлечением текста (включая таблицы
  DOCX и все листы XLSX) и ручной ввод текста.
- Полнотекстовый поиск с нечёткостью, подсветкой фрагментов, фильтрами по
  рубрике и приватности, сортировкой по релевантности и дате.
- Рубрики документов, публичные и приватные документы, история поиска.
- Веб-интерфейс на Django + HTMX и REST API с JWT (Swagger на `/api/docs/`).
- Регистрация с подтверждением email, сброс пароля, смена пароля.
- Ограничение частоты запросов: регистрация, вход, поиск, создание документов.

## Чего сервис не делает

- **Поиск не критичен для сохранения.** Если Elasticsearch недоступен, документ
  всё равно создаётся и хранится в PostgreSQL — он просто временно не находится
  поиском. Так же и Redis: его отказ не мешает входу и загрузке документов.
- **Нет редактирования текста** после создания: только удаление и переключение
  публичности.
- **Чанкинга и векторного поиска нет.** Гибридный поиск (BM25 + kNN) — отдельная
  работа, см. `docs/ARCHITECTURE.md`.

## Стек

| Слой | Что |
|---|---|
| Приложение | Python 3.12, Django 6.0, Django REST Framework, django-htmx |
| Поиск | Elasticsearch 8.11 (общий контейнер), django-elasticsearch-dsl 7.4 |
| Данные | PostgreSQL 17 (общий контейнер, база `diploma`), Redis 8 (общая, база `/1`) |
| Аутентификация | SimpleJWT для API, сессии для веб-интерфейса |
| Извлечение текста | pypdf, python-docx, openpyxl |
| Сборка и запуск | Poetry 2.4.1, gunicorn, Docker, GitHub Actions |

Почему клиент Elasticsearch 7.x при сервере 8.11 — в `docs/ARCHITECTURE.md`.

## Быстрый старт

### Локально

```bash
poetry install                       # зависимости (Python 3.12)
cp .env.example .env                 # DJANGO_DEBUG=True, базы на localhost

# Инфраструктура с портами на хост: PostgreSQL 5432, Redis 6379, Elasticsearch 9200
docker compose -f docker-compose.dev.yml up -d db redis elasticsearch

poetry run python manage.py migrate
poetry run python manage.py createsuperuser
poetry run python manage.py runserver
```

Приложение: http://127.0.0.1:8000

Переиндексация документов в Elasticsearch:

```bash
poetry run python manage.py search_index --rebuild -f
```

### Тесты и линтеры

```bash
poetry run pytest                    # 153 теста, settings_ci: sqlite + мок ES
poetry run black --check --line-length 120 .
poetry run isort --check-only --profile black --line-length 120 .
poetry run flake8 . --max-line-length=120 --ignore=E203,W503,E501
```

Тесты не требуют ни PostgreSQL, ни Redis, ни Elasticsearch: их подменяет
`config/settings_ci.py`. Проверки устойчивости к отказам Elasticsearch и Redis —
в `tests/test_resilience.py`.

## Переменные окружения

Полный список с пояснениями — в `.env.example` (локально) и
`.env.production.example` (сервер). Ключевые:

| Переменная | Смысл |
|---|---|
| `DJANGO_SECRET_KEY` | секрет Django; на сервере генерируется, в репозитории — заглушка |
| `DJANGO_DEBUG` | `True` только локально; в проде включает HSTS и HTTPS-редирект |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | домены через запятую |
| `POSTGRES_*`, `DB_HOST`, `DB_PORT` | база; в контейнере `DB_HOST=postgres` |
| `ELASTICSEARCH_HOST`, `ELASTICSEARCH_PORT` | в контейнере `elasticsearch:9200` |
| `REDIS_URL` | номер базы закреплён за проектом: `/1` |
| `EMAIL_*` | подтверждение почты и сброс пароля |

## API

Интерактивная документация — `/api/docs/` (Swagger). Машиночитаемая схема —
[docs/api/openapi.json](docs/api/openapi.json); она генерируется из кода и
проверяется в CI, поэтому не может разойтись с ним незаметно.

`rubrics` в запросе принимает и список строк, и строку через запятую — так её
отправляет web-форма.

## Проверка состояния

| Адрес | Что проверяет | Когда использовать |
|---|---|---|
| `/health/` | процесс отвечает, зависимости не опрашиваются | liveness, перезапуск контейнера |
| `/health/ready/` | обязательна база; Redis и Elasticsearch в отчёте | healthcheck и гейт деплоя |

`/health/ready/` отвечает `200`, пока жива база, даже если Elasticsearch лежит —
в отчёте он будет `degraded`. Это осознанно: поиск не критичен для работы
приложения.

## Эксплуатация

- Развёртывание, обновление и откат — [docs/DEPLOY.md](docs/DEPLOY.md)
- Устройство приложения и модель данных — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Диагностика, логи, бэкапы, ресурсы — [docs/OPERATIONS.md](docs/OPERATIONS.md)

## Структура репозитория

```
config/            настройки Django, urls, health-эндпоинты
documents/         документы, поиск, индексация, извлечение текста
  constants.py       единые ограничения и валидация
  rubrics.py         список рубрик и его кэш
  signals.py         индексация и сброс кэша (best-effort)
  services/          сервис поиска
users/             кастомная модель пользователя, аутентификация по email
deploy/nginx/      vhost для общего nginx хоста
templates/         шаблоны (Bootstrap + HTMX)
tests/             pytest
docs/              документация
```

## Что за файлы compose

| Файл | Назначение |
|---|---|
| `docker-compose.dev.yml` | локальная разработка: PostgreSQL, Redis и Elasticsearch с портами на хост, приложение можно запускать через `runserver` |
| `docker-compose.yml` | прод-подобный локальный запуск: всё внутри контейнеров, вход через nginx |
| `docker-compose.prod.yml` | сервер: копируется в `/srv/compose/diploma/compose.yaml`, портов не публикует |
