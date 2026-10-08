# Эксплуатация

Хост приложений `infra-dev`: 4 ядра, около 15 ГБ памяти, 58 ГБ диска. На нём
живут ещё десяток контейнеров, поэтому общие ресурсы ломаются тихо, а диск и
память нужно беречь.

## Что проверять первым

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker inspect --format '{{json .State.Health}}' diploma-web | head -c 400
curl -fsS https://docsearch.pyconstrictor.ru/health/ready/ | python3 -m json.tool
```

Ответ `/health/ready/`:

```json
{"status": "ok", "checks": {"database": "ok", "redis": "ok", "elasticsearch": "ok"}}
```

`503` и `"database": "error: ..."` — приложение действительно не работает.
`200` с `degraded` у `redis` или `elasticsearch` — работает, но без кэша или
поиска; это не повод перезапускать контейнер.

## Логи

```bash
docker logs --tail 200 diploma-web                # gunicorn: access и ошибки
docker logs --tail 100 diploma-migrate            # миграции и collectstatic
docker logs --tail 50 nginx
docker exec nginx sh -c 'tail -50 /var/log/nginx/access.log'
```

Ротация задана в compose (`max-size: 10m`, `max-file: 3`). До её введения лог
одного контейнера дорос до 1,7 млн строк — почти всё это `DisallowedHost` от
сканеров, которые ходят по IP. IP добавлен в `ALLOWED_HOSTS`, поэтому вместо
трассировок теперь обычные строки в access-логе.

Признаки в логах:

| Запись | Что значит |
|---|---|
| `Не удалось проиндексировать документ N` | Elasticsearch недоступен или отказал в записи. Документ в базе есть, поиском не находится |
| `Кэш недоступен, лимит ... не применяется` | Redis недоступен, лимиты пропускают запросы |
| `DisallowedHost` | запрос пришёл на хост, которого нет в `ALLOWED_HOSTS` |
| `413 Request Entity Too Large` | ответ nginx до приложения: нет `client_max_body_size` в vhost либо файл больше 20 МБ |

## Диагностика отказов

### Не загружаются документы

Порядок проверки — от внешнего края к приложению:

```bash
# 1. Файл доходит до Django? 403 (нет CSRF) — доходит, 413 — рубит nginx
curl -sS -o /dev/null -w '%{http_code}\n' --resolve docsearch.pyconstrictor.ru:443:127.0.0.1 \
  -X POST --data-binary @файл https://docsearch.pyconstrictor.ru/documents/create/

# 2. Есть ли лимит в vhost
docker exec nginx grep -n client_max_body_size /etc/nginx/conf.d/docsearch.pyconstrictor.ru.conf

# 3. Доступен ли Elasticsearch из приложения
docker exec diploma-web python -c "
from elasticsearch_dsl.connections import connections
print(connections.get_connection().info()['version']['number'])"

# 4. Доступен ли Redis
docker exec diploma-web python -c "
from django.core.cache import cache; cache.set('probe', 1); print('redis:', cache.get('probe'))"
```

Создание документа не зависит от Elasticsearch и Redis: 500 при загрузке — это
база, права на каталог медиа или ошибка в коде, но не поиск.

### Пропали загруженные файлы

```bash
ls -la /srv/data/diploma/media/documents/2026/   # владелец должен быть uid 1000
docker exec diploma-web sh -c 'touch /app/media/.probe && rm /app/media/.probe && echo writable'
```

### Не ищется документ, который точно есть

```bash
# Сколько документов в базе и сколько в индексе
docker exec postgres psql -U diploma -d diploma -c "SELECT count(*) FROM documents_document;"
docker exec diploma-web python -c "
from elasticsearch_dsl.connections import connections
print(connections.get_connection().cat.indices(index='documents', format='json', h='index,health,docs.count,store.size'))"

# Пересобрать индекс из базы (единственный источник правды)
docker exec diploma-web python manage.py search_index --rebuild -f
```

Здоровье индекса должно быть `green`: реплик у индекса нет (`number_of_replicas=0`),
поэтому `yellow` означал бы, что настройки индекса не применились и его нужно
пересоздать.

### Контейнер не становится healthy

```bash
docker inspect --format '{{json .State.Health}}' diploma-web | python3 -m json.tool
docker logs --tail 100 diploma-web
docker logs --tail 100 diploma-migrate
```

Healthcheck опрашивает `/health/ready/`, то есть PostgreSQL. Если база недоступна,
контейнер останется `unhealthy` и деплой откатится на предыдущий образ.

## Бэкапы

Приложение не делает резервных копий. Данные проекта — это база `diploma` и
каталог `/srv/data/diploma/media`.

```bash
# Дамп базы
docker exec postgres pg_dump -U diploma -d diploma -Fc > /srv/backups/diploma/diploma-$(date +%F).dump

# Восстановление
docker exec -i postgres pg_restore -U diploma -d diploma --clean --if-exists < dump
```

Индекс Elasticsearch бэкапить не нужно: он пересобирается из базы командой
`search_index --rebuild -f`.

## Ресурсы и место на диске

```bash
free -h
df -h /
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' | sort -k2 -h
```

Образы diploma удаляются автоматически при деплое: остаются только текущий и
`rollback`. Если места мало, деплой сначала чистит старые теги, а при нехватке
5 ГиБ отказывается разворачиваться — это защита соседних проектов, а не сбой.

## Лишний трафик и регистрации

Публичный домен сканируют боты. Признаки: строки `DisallowedHost` в логах,
регистрации с неподтверждённых адресов.

```bash
# Неподтверждённые пользователи
docker exec postgres psql -U diploma -d diploma -c \
  "SELECT id, email, date_joined FROM users_user WHERE NOT is_email_verified ORDER BY id;"

# Удалить конкретного
docker exec postgres psql -U diploma -d diploma -c "DELETE FROM users_user WHERE id = N;"
```

Регистрация ограничена тремя попытками в час на адрес (`documents/rate_limit.py`),
но при недоступном Redis лимит не применяется — это осознанный выбор в пользу
доступности. Если входящий спам станет проблемой, следующий шаг — капча на
регистрации, а не ужесточение лимита.

Отдельная мера на уровне хоста: сейчас блок `:443` приложения работает сервером
по умолчанию, поэтому запросы по IP попадают в diploma. Общий nginx выиграл бы от
catch-all блока с `return 444` — это правка на хосте, затрагивающая все проекты.

## Сертификат

```bash
docker run --rm -v /srv/data/letsencrypt:/etc/letsencrypt:ro \
  certbot/certbot certificates | grep -E 'Certificate Name|Domains|Expiry'
docker run --rm -v /srv/data/certbot:/var/www/certbot \
  -v /srv/data/letsencrypt:/etc/letsencrypt \
  certbot/certbot renew --webroot -w /var/www/certbot --dry-run
```

Продление — задание cron пользователя деплоя, см. `docs/DEPLOY.md`. Файл
`/srv/data/letsencrypt/archive/*/cert1.pem` в единственном числе означает, что
сертификат ни разу не продлевался.
