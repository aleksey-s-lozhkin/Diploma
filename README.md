# 📄 DocSearch - Поисковая система по документам

[![CI/CD](https://github.com/aleksey-s-lozhkin/Diploma/actions/workflows/deploy.yml/badge.svg)](https://github.com/aleksey-s-lozhkin/Diploma/actions/workflows/deploy.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-6.0-green.svg)](https://www.djangoproject.com/)
[![Elasticsearch](https://img.shields.io/badge/elasticsearch-8.11-blue.svg)](https://www.elastic.co/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Production-готовый сервис для полнотекстового поиска по документам с веб-интерфейсом и REST API.

## ✨ Возможности

### 🔍 Поиск и работа с документами
- Полнотекстовый поиск с поддержкой русского и английского языка (стемминг, стоп-слова)
- Нечёткий поиск (fuzziness) с исправлением опечаток
- Выделение найденных фрагментов в результатах поиска
- Фильтрация по рубрикам и типу доступа (публичные/приватные)
- Сортировка по релевантности и дате создания
- Пагинация результатов (20 документов на страницу)

### 👤 Пользователи и безопасность
- Регистрация и аутентификация с подтверждением email
- JWT-токены для API (access + refresh)
- Сброс пароля через email
- Разграничение доступа к документам (только свои)
- Rate limiting (ограничение частоты запросов)

### 📁 Управление документами
- Создание документов через ручной ввод или загрузку файлов
- Поддержка форматов: PDF, DOCX, XLSX, TXT
- Автоматическое извлечение текста из загруженных файлов
- Публикация/скрытие документов
- История поисковых запросов пользователя

### 🌐 Веб-интерфейс
- Адаптивный дизайн на Bootstrap 5
- Динамическая подгрузка результатов через HTMX
- Дашборд со списком документов пользователя
- Страница истории поиска
- Модальные окна для быстрого просмотра

## 🛠 Технологический стек

| Компонент | Технология |
|-----------|------------|
| **Backend** | Django 6.0 + Django REST Framework |
| **Поисковый движок** | Elasticsearch 8.11 (русский стемминг) |
| **База данных** | PostgreSQL 15 |
| **Кеширование** | Redis 7 |
| **Веб-сервер** | Gunicorn + Nginx |
| **Фронтенд** | Django Templates + HTMX + Bootstrap 5 |
| **Аутентификация** | JWT (djangorestframework-simplejwt) |
| **Контейнеризация** | Docker + Docker Compose |
| **CI/CD** | GitHub Actions |
| **Управление зависимостями** | Poetry |
| **Тестирование** | pytest (покрытие >75%) |

## 📋 Требования

- Python 3.12
- Docker & Docker Compose
- Poetry (для локальной разработки)
- Git

## 🚀 Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/aleksey-s-lozhkin/Diploma.git
cd Diploma
```

### 2. Настройка окружения
Скопируйте и отредактируйте файл с переменными окружения:

```bash
cp .env.example .env
```

Отредактируйте .env файл, указав свои значения:

```env
# Django
DJANGO_SECRET_KEY=your-super-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# PostgreSQL
POSTGRES_DB=docsearch
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-db-password

# Email (для верификации и сброса пароля)
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=465
EMAIL_USE_SSL=True
EMAIL_HOST_USER=your-email@yandex.ru
EMAIL_HOST_PASSWORD=your-app-password
```

### 3. Запуск через Docker Compose
```bash
# Запуск всех сервисов
docker compose up -d --build

# Просмотр логов
docker compose logs -f

# Остановка сервисов
docker compose down
```

Сервисы будут доступны по адресам:

- Веб-интерфейс: http://localhost
- API документация (Swagger): http://localhost/api/docs/
- API документация (ReDoc): http://localhost/api/redoc/
- Health check: http://localhost/health/

### 4. Локальная разработка (без Docker)
```bash
# Установка зависимостей через Poetry
poetry install

# Активация виртуального окружения
poetry shell

# Настройка .env для локальной разработки
cp .env.example .env
# Установите DEBUG=True и DB_HOST=localhost

# Применение миграций
python manage.py migrate

# Создание суперпользователя
python manage.py createsuperuser

# Запуск Elasticsearch и PostgreSQL через Docker Compose (только базы)
docker compose -f docker-compose.dev.yml up -d db elasticsearch redis

# Запуск сервера разработки
python manage.py runserver
```

### 5. Индексация документов в Elasticsearch
После добавления документов выполните переиндексацию:

```bash
# Полная переиндексация всех документов
python manage.py reindex_documents

# Принудительная переиндексация (удаление существующего индекса)
python manage.py reindex_documents --force

# Индексация документов конкретного пользователя
python manage.py reindex_documents --user-id 1

# Индексация одного документа
python manage.py reindex_documents --doc-id 1
```

## 📚 API Документация
### Аутентификация
API использует JWT-токены. Для доступа к защищённым эндпоинтам необходимо добавить заголовок:

```text
Authorization: Bearer <your_access_token>
```
### Основные эндпойнты

## Основные эндпоинты

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/api/user/register/` | Регистрация пользователя |
| POST | `/api/user/login/` | Вход (получение токенов) |
| POST | `/api/user/refresh/` | Обновление access токена |
| GET | `/api/user/profile/` | Профиль пользователя |
| GET | `/api/documents/` | Список документов |
| POST | `/api/documents/` | Создание документа |
| GET | `/api/documents/{id}/` | Получение документа |
| PUT/PATCH | `/api/documents/{id}/` | Обновление документа |
| DELETE | `/api/documents/{id}/` | Удаление документа |
| POST | `/api/search/` | Поиск по документам |
| GET | `/api/rubrics/` | Список рубрик |
| DELETE | `/api/search/history/{id}/` | Удаление из истории поиска |

### Примеры запросов
Регистрация пользователя
```bash
curl -X POST http://localhost/api/user/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123",
    "password2": "securepass123",
    "first_name": "Иван",
    "last_name": "Иванов"
  }'
```
Вход в систему
```bash
curl -X POST http://localhost/api/user/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123"
  }'
```
Поиск документов
```bash
curl -X POST http://localhost/api/search/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "python разработка",
    "rubric": "технологии",
    "privacy": "all",
    "page": 1
  }'
```
Создание документа
```bash
# Текстовый документ
curl -X POST http://localhost/api/documents/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rubrics": ["python", "django", "backend"],
    "text": "Django — это высокоуровневый веб-фреймворк...",
    "is_public": true
  }'

# Загрузка файла
curl -X POST http://localhost/api/documents/ \
  -H "Authorization: Bearer <access_token>" \
  -F "rubrics=python,django" \
  -F "is_public=true" \
  -F "file=@/path/to/document.pdf"
```
Полная документация API доступна в формате OpenAPI:

- [docs/api/openapi.json](docs/api/openapi.json)
- [Postman коллекция](docs/postman/postman_collection.json)

## 🧪 Тестирование
```bash
# Запуск всех тестов
pytest

# Запуск с покрытием
pytest --cov=. --cov-report=html

# Запуск конкретного тестового файла
pytest tests/test_api.py

# Запуск с подробным выводом
pytest -v
```
Требования к покрытию: не менее 75%

## 📁 Структура проекта
```text
Diploma/
├── .env.example                 # Пример переменных окружения
├── .gitignore                   # Игнорируемые файлы
├── .pre-commit-config.yaml      # Pre-commit хуки
├── docker-compose.dev.yml       # Docker Compose для разработки
├── docker-compose.yml           # Docker Compose для продакшена
├── Dockerfile                   # Docker образ приложения
├── manage.py                    # Django management скрипт
├── poetry.lock                  # Lock файл зависимостей
├── pyproject.toml               # Poetry зависимости
├── README.md                    # Документация проекта
│
├── config/                      # Конфигурация проекта
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py              # Основные настройки
│   ├── settings_ci.py           # Настройки для CI/CD
│   ├── urls.py                  # Корневые URL
│   └── wsgi.py
│
├── docs/                        # Документация API
│   ├── api/
│   │   └── openapi.json         # OpenAPI спецификация
│   └── postman/
│       └── postman_collection.json  # Postman коллекция
│
├── documents/                   # Приложение документов
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── documents.py             # Elasticsearch индекс
│   ├── models.py                # Модели Document, SearchHistory
│   ├── rate_limit.py            # Rate limiting
│   ├── serializers.py           # DRF сериализаторы
│   ├── signals.py               # Сигналы для индексации
│   ├── utils.py                 # Утилиты (извлечение текста)
│   │
│   ├── management/
│   │   └── commands/
│   │       └── reindex_documents.py  # Команда переиндексации
│   │
│   ├── migrations/
│   │   └── 0001_initial.py
│   │
│   ├── services/
│   │   └── search_service.py    # Сервис поиска
│   │
│   ├── urls/
│   │   ├── urls_api.py          # API маршруты
│   │   └── urls_web.py          # Web маршруты
│   │
│   └── views/
│       ├── views_api.py         # API представления
│       └── views_web.py         # Web представления (HTMX)
│
├── users/                       # Приложение пользователей
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── backends.py              # Аутентификация по email
│   ├── email_utils.py           # Отправка писем
│   ├── forms.py                 # Веб-формы
│   ├── models.py                # Кастомная модель User
│   ├── serializers.py           # DRF сериализаторы
│   │
│   ├── migrations/
│   │   ├── 0001_initial.py
│   │   ├── 0002_add_email_verification.py
│   │   └── 0003_alter_user_email_verification_token_and_more.py
│   │
│   ├── urls/
│   │   ├── urls_api.py          # API маршруты
│   │   └── urls_web.py          # Web маршруты
│   │
│   └── views/
│       ├── views_api.py         # API представления
│       └── views_web.py         # Web представления
│
├── nginx/                       # Nginx конфигурация
│   ├── default.conf             # Production конфиг
│   ├── default.dev.conf         # Development конфиг
│   └── Dockerfile
│
├── templates/                   # HTML шаблоны
│   ├── base.html                # Базовый шаблон
│   ├── dashboard.html           # Дашборд пользователя
│   ├── document_detail.html     # Детальный просмотр документа
│   ├── document_form.html       # Форма создания документа
│   ├── index.html               # Главная страница (поиск)
│   ├── search_history.html      # История поиска
│   │
│   ├── partials/
│   │   ├── documents_list.html  # Список документов (HTMX)
│   │   └── search_results.html  # Результаты поиска (HTMX)
│   │
│   └── users/
│       ├── change_password.html
│       ├── login.html
│       ├── login_form.html
│       ├── password_reset_confirm.html
│       ├── password_reset_request.html
│       ├── register.html
│       └── register_form.html
│
├── static_src/                  # Исходники статики
│   ├── css/
│   │   ├── bootstrap-icons.min.css
│   │   └── bootstrap.min.css
│   ├── images/
│   │   └── logo.jpeg
│   └── js/
│       ├── bootstrap.bundle.min.js
│       ├── htmx-ext-loading-states.js
│       └── htmx.min.js
│
├── tests/                       # Тесты
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_forms.py
│   ├── test_models.py
│   ├── test_rate_limit.py
│   ├── test_serializers.py
│   ├── test_services.py
│   ├── test_utils.py
│   └── test_web.py
│
└── [Эти папки нужно добавить в .gitignore]
    ├── __pycache__/             # Python кэш (везде)
    ├── htmlcov/                 # Отчёты покрытия тестами
    ├── logs/                    # Логи приложения
    ├── media/                   # Загруженные пользователями файлы
    ├── static/                  # Собранная статика (collectstatic)
    └── .env                     # Переменные окружения (секреты)
```
## 🔧 Управление проектом
### Полезные команды
```bash
# Создание суперпользователя
docker compose exec web python manage.py createsuperuser

# Применение миграций
docker compose exec web python manage.py migrate

# Сбор статики
docker compose exec web python manage.py collectstatic

# Просмотр логов
docker compose logs -f web

# Перезапуск сервиса
docker compose restart web

# Доступ в контейнер
docker compose exec web bash
```

### Очистка данных
```bash
# Удаление всех томов (PostgreSQL, Elasticsearch, Redis)
docker compose down -v

# Пересборка образов без кэша
docker compose build --no-cache
```

## 🚢 Деплой на сервер
Проект настроен на автоматический деплой через GitHub Actions при пуше в ветку main.

### Предварительная настройка
Добавьте секреты в GitHub репозиторий (Settings → Secrets and variables → Actions):
```text
Секрет	                Описание
DEPLOY_HOST	        IP адрес сервера
DEPLOY_USER	        Имя пользователя SSH
SSH_PORT	        Порт SSH (обычно 22)
SSH_PRIVATE_KEY	        Приватный SSH ключ
DJANGO_SECRET_KEY	Секретный ключ Django
ALLOWED_HOSTS	        Разрешённые хосты
CSRF_TRUSTED_ORIGINS	Trusted origins для CSRF
POSTGRES_PASSWORD	Пароль PostgreSQL
EMAIL_*	                Настройки SMTP
```
### На сервере установите Docker и Docker Compose:

```bash
sudo apt update
sudo apt install docker.io docker-compose
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

## Ручной деплой
```bash
# На сервере
git clone https://github.com/aleksey-s-lozhkin/Diploma.git
cd Diploma

# Создание .env файла
cp .env.example .env
# Отредактируйте .env

# Запуск
docker compose up -d --build
```

## 📊 Мониторинг и Health Check
- Health check endpoint: GET /health/ — проверяет состояние PostgreSQL и Elasticsearch
- Логи: docker compose logs -f [service_name]
- Статистика Elasticsearch: curl http://localhost:9200/_cat/indices

## 📄 Лицензия
- MIT © [Aleksey Lozhkin]

## 📞 Контакты
- Автор: Aleksey Lozhkin
- Email: aleksey.s.lozhkin@gmail.com
- GitHub: aleksey-s-lozhkin
