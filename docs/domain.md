# Domain and lifecycle

## Persisted chain

`Task.id` is the stable `work_id`. A Task points to its current immutable TaskSpecification and retains all earlier versions. Attempt has its own ID, references the exact specification and actor configuration used, snapshots the configuration, and owns zero or more Artifacts. Evidence belongs to an Artifact. Database constraints prevent cross-task specification/attempt drift.

Revision `0002` binds each Attempt's specification, work, actor configuration, and `input_state_id`
to one immutable specification tuple. `input_state_id` is the SHA-256 digest of canonical
specification content. `(work_id, ownership_epoch)` is unique and positive on Attempts; the Task
epoch begins at zero and increments when a start commits. Version numbers are positive and unique
within their Task or Agent. Current-specification pointers cannot reference another Task's input.

Database guards prevent rewriting/deleting specifications, configurations, or UUID-identified
domain events, and freeze Attempt identity and snapshots while allowing runtime result/status
updates. A failed event insertion rolls back its Attempt and epoch increment. Audit events do
not store submitted instructions or credential values. See [ADR 0004](adr/0004-database-enforced-history.md).

## Task states

`draft → ready → in_progress → awaiting_review → completed`

- A readiness evaluation may move only draft/ready Tasks between those two states.
- Starting an Attempt re-evaluates every requirement transactionally and moves ready to in-progress.
- `candidate_ready` moves an in-progress Task only to awaiting-review and its Attempt to candidate.
- Only a positive control-plane review can accept the candidate and complete the Task.

Cancelled, failed, blocked, rejected, and retry paths stay explicit; no generic success boolean is authoritative.

## Readiness requirements

The API returns stable codes and remediation text for repository validation, base revision, goal, acceptance criteria, verification, actor, reviewer, limits, secrets, sandbox policy, and dependencies. All truth values are retained so the UI can show `x/y` without hiding which policy failed.

Repository access validation is an explicit control-plane assertion in 0.1. A production validator may later perform remote verification behind a dedicated adapter without changing the policy contract.
