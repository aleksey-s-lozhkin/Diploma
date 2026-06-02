FROM python:3.12-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install poetry==1.8.3
RUN poetry config virtualenvs.create false

WORKDIR /app

# Копирование зависимостей
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-interaction --no-ansi --no-root --without dev

# Копирование всего проекта
COPY . .

# Открытие порта
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
