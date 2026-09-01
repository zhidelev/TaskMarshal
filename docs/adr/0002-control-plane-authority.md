# ADR 0002: Completion and external mutation are control-plane authority

- Status: Accepted
- Date: 2026-09-01

## Decision

Actor output may claim `candidate_ready` or `blocked`; it cannot complete a Task. Completion requires a separate accepted-review transition owned by the control plane. Git credentials, publication, and other external mutation authority remain outside coding-agent sandboxes.

## Consequences

Self-report becomes evidence rather than truth. Malformed output is a typed adapter failure. The 0.1 sandbox adapter denies execution preparation until milestone 0.2 supplies isolation and capabilities.
