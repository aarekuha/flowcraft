# Запуск Non-Dev Сервиса

Этот документ описывает текущий non-dev запуск `flowcraft`.

Это не полноценный production-platform setup с `systemd`, `docker-compose` и TLS, а рабочий сценарий для:
- staging;
- локального non-dev запуска;
- разворачивания на отдельной машине без `--reload`.

## Что считается non-dev в текущем проекте

- backend запускается без `--reload`;
- frontend собирается в `dist/`;
- `dist/` отдается через `nginx`;
- `nginx` проксирует `/api` на backend.

## 1. Подготовить зависимости

Из корня проекта:

```bash
make backend-install
make frontend-install
```

## 2. Подготовить БД

Если нужна новая пустая БД:

```bash
make backend-migrate
```

Если нужен существующий state:
- перенести файл `apps/backend/flowcraft.db`;
- убедиться, что backend потом запускается именно с этим файлом.

## 3. Создать администратора при необходимости

```bash
make backend-create-admin ADMIN_NAME="Demo Admin" ADMIN_PHONE="+7 999 000 0099"
```

Если пароль нужен сразу:

```bash
make backend-create-admin ADMIN_NAME="Demo Admin" ADMIN_PHONE="+7 999 000 0099" ADMIN_PASSWORD="password123"
```

## 4. Запустить backend без dev-режима

Из корня проекта:

```bash
make backend-run
```

Это поднимет backend на:

```text
http://0.0.0.0:8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/api/health
```

## 5. Собрать frontend

Из корня проекта:

```bash
make frontend-build
```

После сборки статические файлы будут здесь:

```text
apps/frontend/dist
```

## 6. Временная проверка без nginx

Если нужно быстро проверить собранный frontend:

```bash
make frontend-preview
```

Это поднимет preview-server на:

```text
http://127.0.0.1:4173
```

Важно:
- `vite preview` подходит для проверки сборки;
- для постоянного non-dev запуска лучше использовать `nginx`.

## 7. Рекомендуемый вариант: nginx

В проекте подготовлен базовый конфиг:

- [flowcraft.conf](/home/alex/projects/flowcraft/infra/nginx/flowcraft.conf)

Что делает конфиг:
- отдает `apps/frontend/dist`;
- проксирует `/api` на `127.0.0.1:8000`;
- поддерживает SPA routing через fallback на `index.html`.

## 8. Как подключить nginx

Собрать frontend:

```bash
make frontend-build
```

Запустить backend:

```bash
make backend-run
```

Дальше использовать конфиг из проекта как шаблон для вашего nginx.

Что нужно подставить:
- абсолютный путь до `apps/frontend/dist`;
- при необходимости имя домена;
- при необходимости TLS.

## 9. Минимальный порядок запуска

```bash
make backend-install
make frontend-install
make backend-migrate
make backend-create-admin ADMIN_NAME="Demo Admin" ADMIN_PHONE="+7 999 000 0099"
make frontend-build
make backend-run
```

После этого:
- либо проверять frontend через `make frontend-preview`;
- либо отдавать `apps/frontend/dist` через `nginx`.

## 10. Ограничения текущего non-dev контура

- база данных сейчас `SQLite`;
- отдельного production-process manager в проекте пока нет;
- нет встроенного `systemd` unit;
- нет `docker-compose.prod`;
- нет TLS-конфига;
- нет внешнего reverse proxy по умолчанию, кроме шаблона `nginx`.

То есть текущий non-dev сценарий пригоден для:
- demo;
- тестовой машины;
- внутреннего стенда;
- аккуратного single-node запуска.

Для серьезного production дальше уже нужны:
- внешний `nginx` или другой proxy;
- сервисный менеджер;
- backup policy для SQLite или переход на PostgreSQL.
