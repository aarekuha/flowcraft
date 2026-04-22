# Flowcraft

Каркас проекта для MVP системы учета времени производственных операций.

## Структура

- `apps/backend` — FastAPI backend.
- `apps/frontend` — Vue 3 frontend.
- `docs/product` — продуктовые сценарии и экранная карта.
- `docs/domain` — доменные сущности и правила.
- `docs/api` — API-контракты.
- `docs/adr` — архитектурные решения.
- `infra` — инфраструктурные конфиги.
- `scripts` — вспомогательные скрипты.

## Быстрый старт

Backend:

```bash
make backend-install
make backend-migrate
make backend-dev
```

Frontend:

```bash
make frontend-install
make frontend-dev
```

## Развертывание

Подробная инструкция для запуска на другой машине:

- [deploy-current-service.md](/home/alex/projects/flowcraft/docs/runbooks/deploy-current-service.md)
