# ADR 0004: Database-enforced input and event history

- Status: Accepted
- Date: 2026-09-02
- Implements: AB-005; strengthens ADR 0003

## Decision

Revision `0002` enforces continuity in both PostgreSQL and SQLite. Revision `0001` remains a
frozen schema snapshot. A Task's current specification must belong to that Task. An Attempt
references one immutable `(specification, work, actor configuration, content hash)` tuple and
has a positive, unique `(work_id, ownership_epoch)`. Task and Attempt identifiers are distinct;
version numbers are positive and unique within their stable Task or Agent identity.

TaskSpecification, AgentConfiguration, and DomainEvent rows are append-only: ordinary SQL cannot
update or delete them. Attempt identity, input reference, epoch, start time, and configuration
snapshot cannot change, and Attempts cannot be deleted/replaced. Its runtime status, actor result,
workflow-run reference, and finish time can still change through control-plane logic. Actor
self-report remains non-authoritative for Task completion. SQLite guards also reject `REPLACE`
conflicts, which otherwise can bypass delete triggers.

The immutable configuration reference is authoritative; the snapshot is a retained execution
copy. Domain events retain independent UUID identities and are inserted in the same transaction
as the consequential change. Their work/attempt IDs are audit references, deliberately not
cascading foreign keys, so audit records are not silently erased by parent retention changes.
No new event-query, update, delete, or publication endpoint is introduced.

## Consequences

Tests and deployments apply Alembic migrations: ORM `create_all()` alone does not install history
guards. CI runs the persistence/API/migration contracts against SQLite and isolated PostgreSQL
schemas, including a fully populated Task → Attempt → Artifact → Evidence chain.

The migration preflight rejects inconsistent existing identities with stable reason codes,
without rewriting data or exposing its contents. Operators must stop writers and back up the
database before migration. SQLite batch rebuilds run on a dedicated migration connection with
foreign-key enforcement off; preflight verifies existing references. Application connections keep
foreign-key enforcement on. Online migrations are required for this data validation.

Append-only guards intentionally block cascaded deletion of referenced history. There is no
row-level history purge in 0.1; a later retention change requires an explicit, audited design.
Dropping an isolated test schema/database or intentionally resetting the local Compose volume is
still supported. Downgrading to `0001` preserves data but removes these guards; downgrading to
`base` destroys the schema. Database owners can change DDL, so migration authority and database
credentials must remain outside coding sandboxes; these guards are not a defense against a DBA.
