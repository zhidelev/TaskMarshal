# Product charter and bounded MVP

TaskMarshal exists to make coding-agent work inspectable, recoverable, and governed by explicit control-plane state. The unit of product value is a logical Task, not a model invocation.

## Ubiquitous language

- **Project** groups repositories and logical work.
- **Repository** is a control-plane configuration and credential reference. Credential values never enter task specifications or coding sandboxes.
- **Task** is stable logical work identified by `work_id`.
- **TaskSpecification** is an immutable, authored version of authoritative task input.
- **Agent** is a stable identity; **AgentConfiguration** is its immutable execution policy version.
- **Attempt** is one execution against one specification and configuration snapshot, identified independently by `attempt_id`.
- **Candidate** is an actor claim that work is ready for review. It is not accepted completion.
- **Artifact** is an output produced by an attempt. **Evidence** is a recorded observation about an artifact.
- **Ownership epoch** prevents stale execution from acting as the current owner.

## Frozen invariants

1. Task is not Attempt.
2. Candidate is not accepted completion.
3. Agent self-report is never authoritative.
4. Authoritative edits create new specification or configuration versions.
5. Readiness is a deterministic list of individually addressable policies, never an LLM score.
6. External publication and mutation authority stays in the control plane; Git credential values stay outside agent sandboxes.
7. Provider SDKs remain behind ports owned by the domain boundary.

## V1 non-goals

V1 does not provide arbitrary workflow DAGs, Kubernetes orchestration, automatic task routing, a generic agent marketplace, multi-company SaaS tenancy, or unbounded enterprise configuration. Isolated disposable execution, automated evidence collection, and publication are later milestones.
