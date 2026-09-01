# Architecture

TaskMarshal 0.1 is a modular monolith with a separately runnable UI and worker. Its dependency direction points inward:

```text
React UI → FastAPI/API service → domain policies and ports
                         ↘ SQL persistence
Adapters (PydanticAI, Temporal, sandbox) → domain ports
```

The domain package imports neither FastAPI/SQLAlchemy nor Temporal, Docker, GitHub, PydanticAI, or model-provider types. `scripts/check_dependencies.py` makes that constraint executable in CI.

## State ownership

The control plane owns Tasks, immutable specification/configuration versions, readiness, attempts, artifacts, evidence, and domain events. An adapter returns structured observations; it does not own Task status. Attempts snapshot configuration and bind to exactly one `(task_specification_id, work_id)` pair through a composite foreign key.

`input_state_id` is the SHA-256 digest of canonical specification content. `ownership_epoch` increments at attempt start. Together they give later workflow code a stable basis for rejecting stale results.

## Protected ports

- `AgentAdapter.execute(ExecutionPackage) -> ActorResult` isolates model providers and validates output.
- `SandboxProvider.prepare/destroy` isolates workspace implementations. The 0.1 implementation denies preparation by default because disposable execution belongs to milestone 0.2.
- `WorkflowEngine.start_attempt` hides Temporal. Manual 0.1 start persists a running Attempt without granting execution authority.

## Failure semantics

Readiness and adapter validation fail closed. API failures use `{ "error": { "code", "message", "details" } }`. Operations emit structured start/success/failure logs with stable reason codes, duration, and `work_id`/`attempt_id` when applicable. Consequential lifecycle events also receive immutable UUID identities in `domain_events`.

See ADRs [0001](adr/0001-modular-monolith-and-ports.md), [0002](adr/0002-control-plane-authority.md), and [0003](adr/0003-versioned-input-state.md).
