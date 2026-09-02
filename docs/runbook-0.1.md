# Milestone 0.1 operator runbook

## Start and verify

1. Install Docker Engine with Compose v2 (supporting `--wait`) and Make. No host language runtime is needed.
2. From a clean checkout, run `make dev`. Compose starts Postgres, Temporal, migrations, API, worker, UI, and Temporal UI in dependency order. Copy `.env.example` to `.env` only for overrides; all defaults are local-only.
3. Run `make smoke`. It runs inside the API container, proves an unready task fails closed without an Attempt, then creates a Project, validated Repository, versioned Agent configuration, Task, TaskSpecification, readiness report, and distinct Attempt.
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
- `docker compose logs api worker temporal db` shows structured API operations and dependency state. Match the `X-Correlation-ID` response header or `error.correlation_id` value to the `correlation_id` log field. Credential values and submitted prompt content are never logged by application code.
- If a migration is missing, `make migration-check` exits non-zero using a disposable database.
  `uv run alembic check` checks the currently configured database without applying migrations.
- If domain code imports infrastructure, `make dependency-check` names the file, line, and prohibited module.
- Use `make down` for normal shutdown. Use `docker compose down --volumes` only when intentionally discarding local database state.

## Readiness and local-only configuration

`make status` shows dependency health separately from application readiness. Postgres checks
connection acceptance; Temporal checks its workflow service; migration must exit successfully
before the API and worker start. API `/health/live` is process liveness while `/health/ready`
requires a database query. Both UIs have HTTP checks. The worker becomes healthy only after its
own Temporal client confirms service health. Failed or timed-out probes remove readiness; a
marker older than 15 seconds also fails closed. Its marker lives on container tmpfs, never on the
host. The worker still does not execute coding workflows in milestone 0.1.

All host ports bind to `127.0.0.1`; none of these unauthenticated services should be exposed publicly.
The public `taskmarshal-local-only` password is deliberately non-production. If overriding
`POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB`, update `DATABASE_URL` consistently (URL-encode
credentials). Initialization variables only apply to an empty volume; they do not rotate existing
database credentials. Keep real secrets out of `.env.example`, and never publish the example stack.

## Retention and isolated verification

Normal shutdown retains the named Postgres volume, including smoke fixtures, until the operator
explicitly resets it. CI tears its stack and volume down even if log collection fails. Sanitized
test/coverage summaries, allowlisted events, and job metrics expire after seven days. Raw reports
and Compose logs are never uploaded; they disappear with the ephemeral runner. Do not collect
real prompts or credential values as evidence. Build caches contain no `.env` files, local
databases, or logs. See [CI quality gates](ci.md) for report policy and local reproduction.

For an isolated test on a machine where the default ports are free, use
`make dev smoke COMPOSE='docker compose -p taskmarshal-check'`. Clean up only that test project
with `docker compose -p taskmarshal-check down --volumes --remove-orphans`. This does not remove the
normal `taskmarshal` development volume. Local pytest scratch data follows pytest's bounded
temporary-directory retention; build and coverage output remains ignored in the checkout.
