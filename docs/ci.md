# CI quality gates (AB-004)

The `quality` workflow runs on every pull request and push to `main`. Jobs use Ubuntu 24.04,
Python 3.13.7, uv 0.8.13, Node 22.18.0, frozen Python/npm lockfiles, and commit-pinned actions.
The GitHub token has read-only repository access, checkout does not persist credentials, and
jobs do not receive repository secrets or production credentials. Do not add secret-bearing
fixtures, credentials, or private prompts to tests or workflow commands.

## Checks

| Check | Gate |
| --- | --- |
| `backend-static` | Ruff lint/format, strict mypy (including worker SDK types), domain dependency direction, disposable migration upgrade/check/downgrade/re-upgrade/check |
| `backend-unit` | Domain policies/transitions, worker health, dependency-check rejection, smoke client, artifact privacy tests |
| `backend-integration` | API/adapter contracts, migration history and failure cases, in-process end-to-end scenario |
| `frontend` | ESLint and React hooks rules, TypeScript, Vitest UI/API tests with coverage, production build |
| `clean-stack` | Build API/worker/UI images, start Postgres/Temporal and applications, wait for readiness, check Postgres model drift, smoke test, tear down |

The first four are fast checks (ten-minute timeout). `clean-stack` is a separate, independently
visible fifteen-minute job, not a prerequisite for the fast checks. Configure these check names
in repository branch protection as appropriate; the workflow does not change repository settings.
No tests are automatically retried or marked `continue-on-error`. Matrix jobs do not cancel each
other on failure. New commits cancel obsolete runs.

## Local reproduction

After `uv sync --frozen --extra dev` and `cd frontend && npm ci`:

```bash
make check              # all fast checks, including both test suites and migration history
make test-backend       # Python tests only
make test-frontend      # UI/API tests only
make migration-check   # fresh temporary SQLite; never migrates DATABASE_URL
make dev smoke         # image builds and full dependency-backed smoke test
docker compose exec -T api alembic check
```

On a supported platform, install `--extra worker` too to reproduce CI's SDK-aware typecheck.
The integration suite checks populated rollback and deterministic revisions. Negative tests prove
unapplied revisions and ORM changes without a revision are rejected by Alembic. Domain import
tests exercise direct, nested, wildcard, and relative prohibited imports; an empty/missing domain
directory fails closed. Stack verification also checks the schema against actual Postgres.

## Reports, privacy, and retention

Each job prepares a fresh `ci-artifacts/` directory using `scripts/ci_artifacts.py`. Uploads occur
only if preparation succeeds, including after failing tests. Missing or malformed input reports
fail preparation: no raw fallback is uploaded. A pre-existing output directory is rejected.

Uploaded artifacts contain only:

- Sanitized JUnit: ordinal test identifiers, pass/fail/error/skip counts, and durations. Test names,
  parameter values, assertion messages, stack traces, properties, stdout, and stderr are removed.
- Numeric coverage totals (`coverage-summary.json`), without source text, file names, or paths.
- Stack events: allowlisted event/reason codes, UUID correlation/work/attempt IDs, and durations.
  Unknown reasons are redacted; unstructured Compose logs and extra fields are discarded.
- Job metrics: a generated correlation ID, stable result code, elapsed seconds from post-checkout
  setup through report preparation, cache hit/miss where the setup action provides it (otherwise
  `null`), workflow attempt number, and automatic flaky rerun count (`0`, retries are disabled).
  GitHub's job UI supplies full duration including artifact upload. A manual workflow rerun is
  not evidence of a flaky test and is recorded separately as `workflow_attempt`.

Artifacts expire after seven days. Raw intermediate reports and Compose logs remain only on the
ephemeral runner and are never uploaded or cached. CI caches package downloads, not test output
or workspaces. Stack teardown always runs, independently of log collection/report generation.
Local reports and build output are ignored by Git and excluded from Docker contexts; local
migration-check databases are deleted when the check exits. Reproduce a failing test locally
for full diagnostics rather than weakening the artifact policy. This adds enforcement only;
domain/API/schema invariants and publication authority are unchanged.
