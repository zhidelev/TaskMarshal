# TaskMarshal

TaskMarshal is a control plane for reliable coding-agent work. Milestone 0.1 provides the first complete operator path: configure a repository and versioned agent, create a logical task with an immutable specification, satisfy a deterministic readiness gate, and start a manually driven attempt.

The core invariant is deliberately visible throughout the code and UI:

```text
Task (stable work_id) → Attempt (attempt_id) → Artifact → Evidence
```

An actor may report a candidate. It cannot mark a Task complete. Completion is a separate, control-plane-owned transition requiring review.

## Run from a clean checkout

Prerequisites: Docker Engine with Compose v2 and Make.

```bash
cp .env.example .env
make dev
make smoke
```

The stack waits for dependency health and application readiness before returning:

- Web UI: <http://localhost:3000>
- API and generated OpenAPI: <http://localhost:8000/docs>
- Temporal UI: <http://localhost:8080>
- Postgres: `127.0.0.1:5432` with explicitly local-only defaults

Stop the stack with `make down`. To remove local database state too, run `docker compose down --volumes` intentionally.

## Local development without containers

Python 3.13, [uv](https://docs.astral.sh/uv/), and Node 22 are required.

```bash
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn taskmarshal.api.main:app --reload

# In a second terminal, with Temporal available at localhost:7233:
uv sync --frozen --extra worker
uv run python -m worker.main

cd frontend
npm ci
npm run dev
```

The Docker worker installs the optional Temporal SDK automatically.

SQLite is the safe backend default when `DATABASE_URL` is absent. Docker Compose and deployment paths use Postgres.

## Quality gates

```bash
make check              # lint, format, typing, import boundaries, tests
uv run alembic check    # fail when model changes lack a migration
docker compose build    # validate production-shaped images
```

CI separates fast backend/frontend checks from the clean-stack end-to-end smoke test and uploads test and Compose logs without credential values.

## Repository map

- `backend/taskmarshal/domain`: pure policies, transitions, and the `AgentAdapter`, `SandboxProvider`, and `WorkflowEngine` ports
- `backend/taskmarshal/api`: FastAPI schemas and application service
- `backend/taskmarshal/persistence`: SQLAlchemy mappings for the durable chain
- `backend/taskmarshal/adapters`: PydanticAI, Temporal, and deny-by-default sandbox adapters
- `frontend`: intentionally operational React UI
- `worker`: Temporal development worker boundary
- `migrations`: reversible Alembic schema history
- `tests`: unit, adapter integration, migration, negative-path, and end-to-end coverage
- `docs`: product charter, architecture, API notes, ADRs, and milestone runbook

See [architecture](docs/architecture.md), [domain model](docs/domain.md), and the [0.1 runbook](docs/runbook-0.1.md).
