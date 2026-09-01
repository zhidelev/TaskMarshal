.PHONY: dev down logs migrate worker test lint typecheck check smoke dependency-check

dev:
	docker compose up --build --wait

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f api worker frontend

migrate:
	uv run alembic upgrade head

worker:
	uv run python -m worker.main

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
	uv run python scripts/smoke.py
