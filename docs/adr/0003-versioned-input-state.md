# ADR 0003: Immutable versioned input and independent attempts

- Status: Accepted
- Date: 2026-09-01

## Decision

Tasks and Agents have stable identities; authoritative content is append-only through TaskSpecification and AgentConfiguration versions. Attempts have independent identities, bind to one work/specification/configuration, snapshot configuration, record the specification digest as `input_state_id`, and capture an incrementing `ownership_epoch`.

## Consequences

History is auditable, retries do not overwrite logical work, and stale later results can be rejected. Schema uniqueness and foreign keys prevent cross-task association drift.
