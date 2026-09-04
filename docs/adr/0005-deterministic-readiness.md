# ADR 0005: Deterministic readiness over the current specification

- Status: Accepted
- Date: 2026-09-04
- Implements: AB-006; refines ADR 0003

## Decision

Task readiness is the conjunction of an ordered set of composable domain policies. Each policy has
a stable code, a Boolean result, and remediation text. Evaluation returns every result and never
uses a model, heuristic score, or actor assertion. Attempt start evaluates the same policies and
fails closed before persisting an Attempt.

Authoritative Task input is an append-only TaskSpecification. Every create request supplies an
author; the control plane assigns the next version, timestamp, identity, and canonical content
digest. A new version becomes current and invalidates the `ready` state until reevaluated. Requests
cannot supply response-owned metadata. Repository and dependency references are restricted to the
Task's Project, and readiness independently rejects mismatched persisted references.

The 0.1 repository check uses an explicit access-validation timestamp plus syntactic repository and
base-revision validation. Remote revision resolution belongs behind a future repository adapter;
it must not introduce an LLM score or expose credentials. Secret requirements are references only,
resolved against control-plane configuration. Sandbox readiness requires external mutation to
remain disabled.

## Consequences

Clients can render an exact `satisfied/total` count and actionable failures without reproducing
server policy. Adding or changing a readiness requirement is a public contract change and requires
tests and documentation. Malformed persisted JSON and missing referenced state evaluate false
rather than being treated as truthy. Specification creation logs correlated start/success/failure
events without logging authoritative content or credential references.

No migration is required: revision `0002` already persists every specification field, immutable
author/timestamp/version history, and the current-specification pointer.
