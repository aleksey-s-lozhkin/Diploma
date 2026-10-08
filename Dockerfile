# syntax=docker/dockerfile:1

# Сборка и запуск разделены: в финальный образ попадают зависимости и исходники,
# без pip-кэша и без сборочных инструментов. Раньше зависимости ставились в тот
# же слой, что и код, а в рантайм уезжали gcc и libpq-dev.

FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    POETRY_VERSION=2.4.1

WORKDIR /app

RUN python -m pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Слой зависимостей кэшируется отдельно от кода: правка приложения не
# переустанавливает пакеты. --only main оставляет в образе только рантайм.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY . .


FROM python:3.12-slim-bookworm AS runtime

# uid и gid 1000 совпадают с владельцем /srv/data/diploma на сервере. Это
# позволяет контейнеру писать медиа и статику в bind-mount, не работая от root
# и не требуя chown на хосте.
RUN groupadd --gid 1000 diploma \
    && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin diploma

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings

COPY --from=builder --chown=diploma:diploma /app /app

USER diploma

EXPOSE 8000

# Проверка через стандартную библиотеку: curl в образ не тянем. Проверяем
# liveness, а зависимости (база) опрашивает readiness в healthcheck compose.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health/', timeout=4)"]

# --access-logfile - обязателен: без него в логах контейнера нет ни одной строки
# о запросах, и разбирать инциденты приходится по косвенным признакам.
# Три воркера на четыре ядра хоста: рядом живут ещё десяток контейнеров.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
