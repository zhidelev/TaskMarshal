.PHONY: dev down status logs migrate worker test lint typecheck check smoke smoke-local dependency-check

COMPOSE ?= docker compose

dev:
	$(COMPOSE) up --build --wait --wait-timeout 240

down:
	$(COMPOSE) down --remove-orphans

status:
	$(COMPOSE) ps --all

logs:
	$(COMPOSE) logs -f api worker frontend

migrate:
	uv run alembic upgrade head

worker:
	uv run --extra worker python -m worker.main

test:
	uv run pytest --cov=taskmarshal --cov-report=term-missing --cov-report=xml

lint:
	uv run ruff check backend worker migrations tests scripts
	uv run ruff format --check backend worker migrations tests scripts
	cd frontend && npm run lint

typecheck:
	uv run mypy
	cd frontend && npm run typecheck

dependency-check:
	uv run python scripts/check_dependencies.py

check: lint typecheck dependency-check test

smoke:
	$(COMPOSE) exec -T -e TASKMARSHAL_API_URL=http://api:8000 api python scripts/smoke.py

smoke-local:
	uv run python scripts/smoke.py
