# Предварительная сборка
FROM python:3.12-slim-bookworm AS builder

# Установка Poetry
RUN pip install --no-cache-dir poetry==1.7.1

WORKDIR /app

# Копируем только файлы с зависимостями
COPY pyproject.toml poetry.lock* ./

# Устанавливаем зависимости (убираем --only main)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Финальная сборка
FROM python:3.12-slim-bookworm

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости из builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем код проекта
COPY . .

# Создаем директории
RUN mkdir -p /app/static /app/media /app/logs

# Создаем пользователя
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2"]
