# ADR 0006: Role-neutral AgentAdapter with immutable execution input

- Status: Accepted
- Date: 2026-09-04
- Implements: AB-007; refines ADRs 0001 and 0002

## Decision

The domain owns one provider-neutral `AgentAdapter` protocol. Its `execute` method accepts a frozen
`ExecutionPackage` containing a requested actor/reviewer role and a typed, frozen snapshot of one
immutable AgentConfiguration version. It returns `ActorResult | ReviewResult`; both variants carry
validated provider-neutral `UsageMetadata`. Actor and review outcomes remain distinct types because
they have different lifecycle authority.

The PydanticAI implementation remains in the adapters package. It chooses a strict role-specific
output schema, treats task/repository content as delimited untrusted data, validates output and
usage, and maps all provider/validation failures to stable redacted reason codes. It has no sandbox,
credential, publication, or Task-transition authority. An `approved` ReviewResult is an observation
consumed by later control-plane policy, not permission for the adapter to complete a Task.
The adapter enforces the configuration timeout around provider invocation and fails closed when
reported cost exceeds a non-null configuration cap.

Each persisted AgentConfiguration version has its own required name, role eligibility,
adapter/provider/model selectors, instructions, concurrency and timeout policy, optional cost cap,
author, and timestamp. Revision `0003` adds the name with a stable legacy default so populated
immutable histories can upgrade without updates or disabled guards.

## Consequences

Provider implementations and SDK types remain replaceable and outside the domain. Actor/reviewer
callers share identity, input, usage, failure, and observability contracts without conflating their
results. The execution package cannot be rewritten after construction, and its requested role must
be eligible under its snapshot.

Adapter events include correlation, work and attempt IDs, role, duration, and stable reason codes;
they exclude instructions, prompts, output, credentials, and raw provider exceptions. Invalid
structure or usage fails closed. Adding a role or result authority requires a domain/API review and
an ADR rather than provider-specific branching in workflow policy.
