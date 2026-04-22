FRONTEND_DIR := apps/frontend
BACKEND_DIR := apps/backend
NPM := npm
PYTHON := python3

.PHONY: frontend-install frontend-dev frontend-build frontend-preview backend-install backend-dev backend-run backend-migrate backend-seed-demo backend-seed-real-10 backend-create-admin backend-test backend-lint backend-typecheck

frontend-install:
	cd $(FRONTEND_DIR) && $(NPM) install

frontend-dev:
	cd $(FRONTEND_DIR) && $(NPM) run dev

frontend-build:
	cd $(FRONTEND_DIR) && $(NPM) run build

frontend-preview:
	cd $(FRONTEND_DIR) && $(NPM) run preview -- --host 0.0.0.0 --port 4173

backend-install:
	cd $(BACKEND_DIR) && $(PYTHON) -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

backend-dev:
	cd $(BACKEND_DIR) && . .venv/bin/activate && uvicorn app.main:app --reload

backend-run:
	cd $(BACKEND_DIR) && . .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

backend-migrate:
	cd $(BACKEND_DIR) && . .venv/bin/activate && alembic upgrade head

backend-seed-demo:
	cd $(BACKEND_DIR) && . .venv/bin/activate && python -m app.scripts.seed_demo

backend-seed-real-10:
	cd $(BACKEND_DIR) && . .venv/bin/activate && python -m app.scripts.seed_real_products

backend-create-admin:
	cd $(BACKEND_DIR) && . .venv/bin/activate && python -m app.scripts.create_admin --name "$(ADMIN_NAME)" --phone "$(ADMIN_PHONE)" $(if $(ADMIN_PASSWORD),--password "$(ADMIN_PASSWORD)",)

backend-test:
	cd $(BACKEND_DIR) && . .venv/bin/activate && pytest

backend-lint:
	cd $(BACKEND_DIR) && . .venv/bin/activate && ruff check .

backend-typecheck:
	cd $(BACKEND_DIR) && . .venv/bin/activate && mypy .
