# Развертывание Текущего Сервиса

Этот документ описывает, как запустить текущий `flowcraft` на другой машине.

Он покрывает 2 сценария:
- запуск с текущей БД, чтобы получить именно текущее состояние данных;
- запуск с новой пустой БД, чтобы поднять только схему и сервисы.

## Что нужно на машине

- `git`
- `python 3.12+`
- `node 20+`
- `npm`

Проверка:

```bash
python3 --version
node --version
npm --version
```

## 1. Получить проект

Если переносится весь текущий workspace, достаточно скопировать каталог проекта целиком.

Если используется git-клон:

```bash
git clone <repo-url> flowcraft
cd flowcraft
```

## 2. Установить зависимости

Из корня проекта:

```bash
make backend-install
make frontend-install
```

## 3. Поднять backend-схему

Если нужна новая пустая БД:

```bash
make backend-migrate
```

Важно:
- backend использует SQLite по абсолютному пути внутри проекта;
- файл БД ожидается здесь:
  - `apps/backend/flowcraft.db`

## 4. Если нужен именно текущий набор данных

Нужно перенести файл:

```text
apps/backend/flowcraft.db
```

Тогда на другой машине будет доступно текущее состояние данных, а не пустая схема.

Если этот файл переносится:
- сначала скопировать его в `apps/backend/flowcraft.db`;
- потом уже запускать backend.

Текущий минимальный набор данных в этой БД:
- один администратор
- `5` примерных изделий

## 5. Запустить backend

Из корня проекта:

```bash
make backend-dev
```

Backend поднимается на:

```text
http://127.0.0.1:8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/api/health
```

## 6. Запустить frontend

Во втором терминале:

```bash
make frontend-dev
```

Frontend поднимается на:

```text
http://127.0.0.1:5173
```

Vite уже проксирует `/api` на backend `127.0.0.1:8000`.

## 7. Порядок запуска

Рекомендуемый порядок:

```bash
make backend-install
make frontend-install
make backend-migrate
make backend-dev
make frontend-dev
```

Если переносится текущая БД:

```bash
make backend-install
make frontend-install
# скопировать apps/backend/flowcraft.db
make backend-dev
make frontend-dev
```

## 8. Что делать, если вход не работает

Проверить:
- что backend действительно запущен после последних изменений;
- что используется именно `apps/backend/flowcraft.db`;
- что не висит старый процесс backend с открытым старым SQLite-файлом.

Если БД недавно заменяли:
- полностью остановить backend;
- запустить его заново:

```bash
make backend-dev
```

## 9. Что делать, если нужна пустая среда

Удалить текущую SQLite БД и поднять схему заново:

```bash
rm -f apps/backend/flowcraft.db
make backend-migrate
```

После этого сервис стартует с пустой схемой.

## 10. Полезные команды

Проверка backend:

```bash
make backend-test
make backend-lint
make backend-typecheck
```

Проверка frontend:

```bash
cd apps/frontend
npm exec tsc -- --noEmit --skipLibCheck
```

Создание администратора:

```bash
make backend-create-admin ADMIN_NAME="Demo Admin" ADMIN_PHONE="+7 999 000 0099"
```

Если нужен пароль сразу:

```bash
make backend-create-admin ADMIN_NAME="Demo Admin" ADMIN_PHONE="+7 999 000 0099" ADMIN_PASSWORD="password123"
```

## 11. Что важно для Codex на другой машине

Если другой Codex должен поднять сервис без уточнений, ему достаточно следовать такому сценарию:

1. Открыть корень проекта.
2. Выполнить `make backend-install`.
3. Выполнить `make frontend-install`.
4. Если файл `apps/backend/flowcraft.db` уже есть и нужен текущий state, использовать его.
5. Иначе выполнить `make backend-migrate`.
6. Запустить `make backend-dev`.
7. Во втором терминале запустить `make frontend-dev`.

Если нужен именно текущий пользователь и текущие изделия, без переноса БД это состояние автоматически не восстановится.
