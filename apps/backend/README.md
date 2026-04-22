# Backend

Серверная часть проекта на `FastAPI`.

## Структура

- `app/api` — HTTP-слой и роуты.
- `app/domain` — предметная модель.
- `app/services` — прикладные сценарии.
- `app/repositories` — доступ к данным.
- `app/models` — ORM-модели.
- `app/schemas` — схемы запросов и ответов.
- `app/core` — настройки и инфраструктурные зависимости.

## Команды

Из корня проекта:

```bash
make backend-install
make backend-migrate
make backend-create-admin ADMIN_NAME="Demo Admin" ADMIN_PHONE="+7 999 000 0099"
make backend-seed-demo
make backend-dev
make backend-test
make backend-lint
make backend-typecheck
```

`make backend-seed-demo` добавляет тестовые данные для разработки и доводит набор demo-изделий до 50 штук без бесконтрольного дублирования при повторном запуске.

`make backend-create-admin` создает или обновляет администратора по номеру телефона. Пароль можно передать опционально через `ADMIN_PASSWORD`; если его не передавать, пользователь войдет через сценарий первичной установки пароля.

## API

- `GET /api/products` — список изделий.
- `GET /api/products/{id}` — просмотр одного изделия.
- `POST /api/products` — создание изделия с деревом операций.
- `DELETE /api/products/{id}` — удаление изделия.
- `PATCH /api/products/{id}/status` — смена активности изделия.
