# Milestone 0.1 operator runbook

## Start and verify

1. From a clean checkout, copy `.env.example` to `.env`. Values are local-only and contain no production secret.
2. Run `make dev`. Compose starts Postgres, Temporal, migrations, API, worker, UI, and Temporal UI in dependency order.
3. Run `make smoke`. The smoke scenario creates a Project, validated Repository, versioned Agent configuration, Task, TaskSpecification, readiness report, and distinct Attempt.
4. Open the UI at <http://localhost:3000>. The API readiness probe is <http://localhost:8000/health/ready>.

## Manual demonstration

1. Create a Project.
2. Configure a Repository. Use only a credential reference and assert access validation.
3. Create an Agent; the UI creates configuration v1 eligible for actor and reviewer roles.
4. Create a Task and specification v1 with every required input.
5. Open the Task. Confirm all readiness policies show satisfied.
6. Start the manual Attempt. Record that `work_id` and `attempt_id` differ and the Task is `in_progress`, not completed.
7. Create the next specification version from the Task detail. Confirm history retains v1 and readiness is evaluated against v2.

## Negative-path demonstration

Create a Task without a specification and POST its attempts endpoint. It must return HTTP 409 `task.not_ready`, enumerate stable remediation codes, retain Task `draft`, and persist no Attempt.

## Troubleshooting

- `docker compose ps` distinguishes dependency startup from ready applications.
- `docker compose logs api worker temporal db` shows structured API operations and dependency state. Credential values are never logged by application code.
- If a migration is missing, `uv run alembic check` exits non-zero.
- If domain code imports infrastructure, `make dependency-check` names the file, line, and prohibited module.
- Use `make down` for normal shutdown. Use `docker compose down --volumes` only when intentionally discarding local database state.
