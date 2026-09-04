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

Each specification version must include repository and base revision, goal, acceptance criteria,
verification commands, constraints, actor and reviewer configurations, execution limits, required
secret references, sandbox policy, dependencies, and author. Saving an edit creates a new row and
returns a previously ready Task to `draft`; open its readiness view to evaluate the new current
version. Never copy `id`, `task_id`, `version`, `authored_at`, or `content_hash` into the create
request—those are control-plane-owned response fields.

## Negative-path demonstration

Create a Task without a specification and POST its attempts endpoint. It must return HTTP 409 `task.not_ready`, enumerate stable remediation codes, retain Task `draft`, and persist no Attempt.

For a broader check, GET `/api/v1/tasks/{work_id}/readiness`: the response always contains all 11
requirements and their remediation text. A cross-project repository or dependency is rejected at
specification creation with `repository.project_mismatch` or `dependency.project_mismatch`.

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

### Core schema upgrade and rollback (AB-005)

Stop application writers and back up existing data before running `uv run alembic upgrade head`
(or letting Compose's migration service do so). Current head is `0002`; revision `0001` is unchanged.
Run `uv run alembic current` and `uv run alembic check` afterward. SQLite needs an online,
dedicated migration connection; the Alembic runner leaves FK enforcement off only on that
connection for batch rebuilds, while application connections enforce it.

`migration.identity_conflict` means existing Task/specification/configuration/input/epoch data is
inconsistent; `migration.foreign_key_conflict` identifies broken SQLite references. The migration
refuses to repair or discard that data. Investigate privately from the backup, resolve the
inconsistency through an approved repair, then retry. Never paste database rows or credentials
into logs. Percent-encoded credentials and connection options are supported in `DATABASE_URL`.

`uv run alembic downgrade 0001` preserves rows but removes identity/history guards; keep writers
stopped until re-upgraded. `downgrade base` drops all core tables and is only for disposable
verification or an explicitly approved destructive reset. Append-only history has no row-purge
API in 0.1, and cascaded parent deletion fails if it would remove protected history.

`uv run pytest` runs migrated SQLite tests. For a disposable PostgreSQL server, also pass
`--postgres-url=postgresql+psycopg://USER:PASSWORD@HOST:PORT/TEST_DB`; only use test credentials.
Each test creates its own UUID-named schema and drops that schema in fixture cleanup. CI enables
this path. Both databases run empty/full-chain forward/rollback tests, invalid-existing-data
preflight tests, immutable-history checks, and API transaction rollback tests.

### Retention

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
