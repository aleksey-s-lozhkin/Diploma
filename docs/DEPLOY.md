# Развёртывание diploma

## Схема

diploma живёт на хосте приложений `infra-dev` вместе с другими проектами и не
поднимает собственных PostgreSQL, Redis, Elasticsearch и nginx — он пользуется
общими контейнерами в сети `infra`.

```text
docsearch.pyconstrictor.ru → nginx → diploma-web:8000
                                        ├── postgres:5432        (база diploma)
                                        ├── redis:6379/1         (кэш и лимиты)
                                        └── elasticsearch:9200   (индекс documents)
```

`diploma-web` не публикует ни одного порта на хост. nginx находит его по имени
контейнера в сети `infra`, поэтому снаружи приложение доступно только по HTTPS и
только с заголовками, которые проставил прокси.

Поиск и кэш — не критичные зависимости: при отказе Elasticsearch документы
продолжают создаваться, при отказе Redis — продолжает работать вход.
`/health/ready/` сообщит о них как о `degraded`.

## Раскладка на сервере

| Путь | Что |
|---|---|
| `/srv/compose/diploma/compose.yaml` | `docker-compose.prod.yml` из репозитория |
| `/srv/compose/diploma/.env` | только образ и путь к окружению, без секретов |
| `/srv/config/env/diploma.env` | окружение и секреты приложения, права `600` |
| `/srv/config/nginx/conf.d/docsearch.pyconstrictor.ru.conf` | vhost в общем nginx |
| `/srv/data/diploma/static` | собранная статика, её отдаёт nginx |
| `/srv/data/diploma/media` | загруженные документы |
| `/srv/data/letsencrypt` | сертификаты (общий для всех проектов, владелец root) |
| `/srv/data/certbot` | ACME-каталог для продления (владелец root) |

Каталоги статики и медиа принадлежат uid 1000 — тому же, под которым работает
контейнер. Поэтому `collectstatic` и загрузка файлов идут без root и без `chown`.

## Что должно быть готово

- DNS `docsearch.pyconstrictor.ru` указывает на адрес хоста, порты 80 и 443
  открыты наружу.
- Есть Docker и внешняя сеть `infra`: `docker network inspect infra`.
- Работают общие контейнеры `postgres`, `redis`, `elasticsearch`, `nginx`.
- Пользователь деплоя входит в группу `docker`.
- Общий nginx смонтирован на `/srv/config/nginx/conf.d` и на
  `/srv/data/diploma/{static,media}`:

  ```yaml
  # /srv/compose/nginx/compose.yaml
        - /srv/config/nginx/conf.d:/etc/nginx/conf.d:ro
        - /srv/data/certbot:/var/www/certbot:ro
        - /srv/data/letsencrypt:/etc/letsencrypt:ro
        - /srv/data/diploma/static:/var/www/diploma/static:ro
        - /srv/data/diploma/media:/var/www/diploma/media:ro
  ```

## 1. База и роль в общем PostgreSQL

```bash
docker exec -it postgres psql -U postgres -d postgres
```

```sql
CREATE ROLE diploma LOGIN PASSWORD 'CHANGE_ME';
CREATE DATABASE diploma OWNER diploma;
\c diploma
GRANT ALL ON SCHEMA public TO diploma;
\q
```

Проверка:

```bash
docker exec postgres psql -U diploma -d diploma -c "SELECT current_database(), current_user"
```

## 2. Окружение приложения

```bash
cp .env.production.example /srv/config/env/diploma.env
chmod 600 /srv/config/env/diploma.env
nano /srv/config/env/diploma.env
```

Обязательно заменить:

- **`DJANGO_SECRET_KEY`** — `python -c "import secrets; print(secrets.token_urlsafe(64))"`;
- **`POSTGRES_PASSWORD`** — тот же, что у роли `diploma`;
- **`EMAIL_HOST_PASSWORD`** — пароль приложения Яндекс.Почты;
- **`REDIS_URL`** — база `/1`. База `/0` занята Самогоном: общий номер означает,
  что `cache.clear()` одного проекта стирает ключи другого. `/3`, `/4`, `/5`
  заняты лаптем;
- **`ALLOWED_HOSTS`** — домен и IP хоста.

`ELASTICSEARCH_HOST=elasticsearch` менять не нужно, индекс `documents`
принадлежит этому проекту.

## 3. Файлы compose

```bash
scp docker-compose.prod.yml deploy-user@host:/srv/compose/diploma/compose.yaml
```

Рядом `.env` — без секретов, только то, что compose подставляет при разборе:

```bash
cat > /srv/compose/diploma/.env <<'EOF'
DIPLOMA_IMAGE=alserloz/diploma:latest
DIPLOMA_ENV_FILE=/srv/config/env/diploma.env
EOF
```

Проверить, что файл разбирается, ничего не запуская:

```bash
cd /srv/compose/diploma
DIPLOMA_IMAGE=alserloz/diploma:latest docker compose -f compose.yaml config --quiet
```

## 4. Сертификат Let's Encrypt

Сертификат выпускается **до** установки боевого vhost: тот ссылается на файлы
сертификата, и nginx не стартует, пока их нет. Сначала временный конфиг только с
проверочным путём:

```bash
cat > /srv/config/nginx/conf.d/docsearch-acme.conf <<'NGINX'
server {
    listen 80;
    server_name docsearch.pyconstrictor.ru;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 503; }
}
NGINX
docker exec nginx nginx -t && docker exec nginx nginx -s reload
```

Убедиться, что проверочный путь доступен снаружи (каталог `/srv/data/certbot`
принадлежит root, поэтому файл создаётся контейнером):

```bash
docker run --rm -v /srv/data/certbot:/var/www/certbot alpine:3 \
  sh -c 'mkdir -p /var/www/certbot/.well-known/acme-challenge && echo ok > /var/www/certbot/.well-known/acme-challenge/probe'
curl -fsS http://docsearch.pyconstrictor.ru/.well-known/acme-challenge/probe
docker run --rm -v /srv/data/certbot:/var/www/certbot alpine:3 \
  sh -c 'rm -rf /var/www/certbot/.well-known'
```

Выпуск:

```bash
docker run --rm \
  -v /srv/data/certbot:/var/www/certbot \
  -v /srv/data/letsencrypt:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d docsearch.pyconstrictor.ru \
  --email ВАШ_ЯЩИК@pyconstrictor.ru --agree-tos --no-eff-email --non-interactive
```

Установка боевого vhost (временный обязательно удалить: два блока с одним
`server_name` nginx считает дубликатом):

```bash
scp deploy/nginx/docsearch.pyconstrictor.ru.conf deploy-user@host:/srv/config/nginx/conf.d/
ssh deploy-user@host 'rm -f /srv/config/nginx/conf.d/docsearch-acme.conf'
docker exec nginx nginx -t && docker exec nginx nginx -s reload
```

В vhost обязательна строка `client_max_body_size 20m`. Без неё действует дефолт
nginx в 1 МБ, и любая загрузка больше мегабайта получает `413 Request Entity Too
Large` **до** Django — в логах приложения при этом пусто. Именно это однажды
выглядело как «перестало работать добавление документов».

## 5. Первый деплой

```bash
cd /srv/compose/diploma
DIPLOMA_IMAGE=alserloz/diploma:latest docker compose -f compose.yaml pull
DIPLOMA_IMAGE=alserloz/diploma:latest docker compose -f compose.yaml up -d --no-build
docker compose ps
docker inspect --format '{{json .State.Health}}' diploma-web
```

Порядок: сервис `migrate` применяет миграции и собирает статику, и только после
его успешного выхода стартует `web` (`depends_on: service_completed_successfully`).
Неудачная миграция не оставит работающее приложение на неготовой базе.

При переходе с прежнего compose (там сервис назывался `diploma`, а не `web`)
добавьте `--remove-orphans`: контейнер с тем же именем, но другими метками,
иначе останется висеть и займёт имя. Автоматический деплой делает это сам.

Проверка:

```bash
curl -fsS https://docsearch.pyconstrictor.ru/health/
curl -fsS https://docsearch.pyconstrictor.ru/health/ready/
docker port diploma-web     # пусто: портов на хост нет
```

После первого деплоя индекс стоит пересобрать один раз:

```bash
docker exec diploma-web python manage.py search_index --rebuild -f
```

Индекс, созданный прежней версией кода, содержит одну реплику и на однонодовом
кластере навсегда остаётся в состоянии `yellow`. В коде реплик теперь 0, но
настройки применяются только при пересоздании индекса. Пересборка занимает
секунды и берёт данные из PostgreSQL — он единственный источник правды. В
автоматический деплой шаг не вынесен намеренно: раньше пересборка стояла в
команде запуска, и недоступный Elasticsearch не давал контейнеру подняться.

## 6. Автоматический деплой

Пуш в `main` запускает `publish-deploy.yml`: проверки → сборка образа с тегами
`latest` и `<sha>` → деплой именно `<sha>` по SSH.

Секреты репозитория (environment `production`):

| Секрет | Что внутри |
|---|---|
| `DOCKERHUB_USERNAME` | логин Docker Hub |
| `DOCKERHUB_TOKEN` | access token Docker Hub, не пароль |
| `DEPLOY_SSH_PRIVATE_KEY` | приватный ключ деплоя |
| `DEPLOY_SSH_KEY_PASSPHRASE` | парольная фраза ключа; пустая строка, если её нет |
| `DEPLOY_SSH_KNOWN_HOSTS` | вывод `ssh-keyscan -p <порт> <хост>` |
| `DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER` | адрес, порт и пользователь SSH |

Что делает деплой на сервере:

1. Запоминает работающий образ и ставит на него локальный тег `rollback`.
2. Проверяет свободное место: диск общий с другими проектами, и забить его
   образами diploma означает уронить соседей. При нехватке удаляет старые теги.
3. Загружает образ и поднимает сервисы.
4. Ждёт статус `healthy` до 180 секунд. Healthcheck проверяет `/health/ready/`,
   то есть и PostgreSQL.
5. Перезагружает nginx: пересозданный контейнер получил новый адрес в сети, и без
   `reload` часть запросов ушла бы в 502.
6. При любой ошибке возвращает предыдущий образ из тега `rollback`.

## 7. Обновление и откат

Обновление — пуш в `main`. Вручную:

```bash
cd /srv/compose/diploma
DIPLOMA_IMAGE=alserloz/diploma:<sha> docker compose -f compose.yaml pull
DIPLOMA_IMAGE=alserloz/diploma:<sha> docker compose -f compose.yaml up -d --no-build
```

Откат:

```bash
cd /srv/compose/diploma
DIPLOMA_IMAGE=alserloz/diploma:rollback docker compose -f compose.yaml up -d --no-build
docker exec nginx nginx -t && docker exec nginx nginx -s reload
```

**Откат не откатывает миграции.** Автоматика возвращает код и контейнеры, но
схема базы остаётся той, что применил неудачный деплой. Поэтому миграции должны
быть совместимы с предыдущей версией: сначала добавление полей и таблиц, удаление
старых — отдельным релизом.

## 8. Продление сертификата

Продлением занимается задание в crontab пользователя деплоя (дважды в день,
certbot обращается к Let's Encrypt только если до истечения меньше 30 дней):

```cron
17 3,15 * * * /usr/bin/docker run --rm \
  -v /srv/data/certbot:/var/www/certbot \
  -v /srv/data/letsencrypt:/etc/letsencrypt \
  certbot/certbot renew --webroot -w /var/www/certbot --quiet \
  >> /home/alserloz/certbot-renew.log 2>&1 \
  && /usr/bin/docker exec nginx nginx -s reload >> /home/alserloz/certbot-renew.log 2>&1
```

Проверка механизма без изменений:

```bash
docker run --rm -v /srv/data/certbot:/var/www/certbot \
  -v /srv/data/letsencrypt:/etc/letsencrypt \
  certbot/certbot renew --webroot -w /var/www/certbot --dry-run
```

Хостовый `certbot.timer` здесь не помогает: он продлевает `/etc/letsencrypt`
хоста, а контейнерный nginx смонтирован на `/srv/data/letsencrypt`.

## Чего автоматика не делает

- **Не обновляет vhost.** `deploy/nginx/docsearch.pyconstrictor.ru.conf`
  копируется в общий nginx вручную.
- **Не откатывает миграции.**
- **Не обновляет `.env`.** Изменения `ALLOWED_HOSTS` или `REDIS_URL` применяются
  только при пересоздании контейнера, то есть при следующем деплое.
- **Не делает бэкапы.** См. `docs/OPERATIONS.md`.
- **Не управляет общими PostgreSQL, Redis, Elasticsearch и nginx.**
- **Не хранит секреты.** Всё, что нужно приложению, лежит в
  `/srv/config/env/diploma.env` на сервере.
