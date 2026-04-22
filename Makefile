FRONTEND_DIR := apps/frontend
BACKEND_DIR := apps/backend
NPM := npm
PYTHON := python3

.PHONY: frontend-install frontend-dev backend-install backend-dev backend-migrate backend-seed-demo backend-create-admin backend-test backend-lint backend-typecheck

frontend-install:
	cd $(FRONTEND_DIR) && $(NPM) install

frontend-dev:
	cd $(FRONTEND_DIR) && $(NPM) run dev

backend-install:
	cd $(BACKEND_DIR) && $(PYTHON) -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

backend-dev:
	cd $(BACKEND_DIR) && . .venv/bin/activate && uvicorn app.main:app --reload

backend-migrate:
	cd $(BACKEND_DIR) && . .venv/bin/activate && alembic upgrade head

backend-seed-demo:
	cd $(BACKEND_DIR) && . .venv/bin/activate && python -m app.scripts.seed_demo

backend-create-admin:
	cd $(BACKEND_DIR) && . .venv/bin/activate && python -m app.scripts.create_admin --name "$(ADMIN_NAME)" --phone "$(ADMIN_PHONE)" $(if $(ADMIN_PASSWORD),--password "$(ADMIN_PASSWORD)",)

backend-test:
	cd $(BACKEND_DIR) && . .venv/bin/activate && pytest

backend-lint:
	cd $(BACKEND_DIR) && . .venv/bin/activate && ruff check .

backend-typecheck:
	cd $(BACKEND_DIR) && . .venv/bin/activate && mypy .
