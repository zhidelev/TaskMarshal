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

## Agent configurations and results

`Agent` is a stable identity. Each `AgentConfiguration` is an immutable, named version containing
role eligibility, adapter/provider/model selectors, instructions, concurrency, timeout, an optional
configuration-level cost cap, author, and timestamp. A null configuration cost cap means no
additional Agent-level cap; every TaskSpecification still supplies its required execution cost
limit. Revision `0003` adds the version-owned name and assigns `Legacy configuration` to existing
rows without rewriting their protected history.

The provider-neutral `AgentAdapter` accepts an immutable `ExecutionPackage`. The package identifies
the Task, Attempt, input state, ownership epoch, requested `AgentRole`, immutable task inputs, and a
frozen `AgentConfigurationSnapshot`. An actor returns `ActorResult`; a reviewer returns
`ReviewResult`; both contain validated `UsageMetadata`. Actor candidate claims and reviewer approval
remain observations. Neither result can mutate or complete a Task without control-plane policy.

## Task states

`draft → ready → in_progress → awaiting_review → completed`

- A readiness evaluation may move only draft/ready Tasks between those two states.
- Starting an Attempt re-evaluates every requirement transactionally and moves ready to in-progress.
- `candidate_ready` moves an in-progress Task only to awaiting-review and its Attempt to candidate.
- Only a positive control-plane review can accept the candidate and complete the Task.

Cancelled, failed, blocked, rejected, and retry paths stay explicit; no generic success boolean is authoritative.

## Readiness requirements

Readiness is a deterministic conjunction of independently auditable policies. It never invokes a
model or converts an LLM score into state. The API always returns all 11 truth values, stable codes,
and remediation text so clients can show `satisfied/total` without hiding failures:

| Code | Satisfied when |
| --- | --- |
| `repository.validated` | The repository belongs to the Task's Project, has a safe URL, and has a control-plane validation timestamp. |
| `base_revision.present` | The current specification contains a non-blank immutable revision reference. |
| `goal.present` | The current specification contains a non-blank goal. |
| `acceptance_criteria.present` | At least one non-blank criterion is present. |
| `verification.present` | At least one non-blank verification command is present. |
| `actor.configured` | The immutable actor configuration exists and is actor-eligible. |
| `reviewer.configured` | The immutable reviewer configuration exists and is reviewer-eligible. |
| `limits.present` | Timeout, token, and finite non-negative cost limits have valid types and ranges. |
| `secrets.available` | Every unique required secret reference is registered on the selected repository. Empty requirements are valid; secret values are never accepted here. |
| `sandbox_policy.present` | Network mode is bounded, writable paths are unique and absolute, and external mutation is disabled. |
| `dependencies.completed` | Every unique, same-project dependency exists and is `completed`; missing or mismatched dependencies fail closed. |

Creating a specification always appends the next version with the supplied `authored_by` and a
server timestamp, updates the Task's current pointer, and returns a ready Task to `draft` until the
new version is evaluated. Server-generated identity, version, timestamp, and digest fields are
rejected if replayed in a create request. Repository and dependency references cannot cross the
Task's Project boundary.

Repository access validation is an explicit control-plane assertion in 0.1. A production validator may later perform remote verification behind a dedicated adapter without changing the policy contract.
