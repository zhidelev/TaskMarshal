# ADR 0001: Modular monolith with protected ports

- Status: Accepted
- Date: 2026-09-01

## Decision

Build the control plane as a Python modular monolith plus React UI and Temporal worker. Domain policy owns provider-neutral `AgentAdapter`, `SandboxProvider`, and `WorkflowEngine` protocols. PydanticAI, Temporal, Docker, Git hosts, and persistence implementations remain outside the domain package.

## Consequences

The first milestone stays simple to deploy while retaining replaceable infrastructure. An AST dependency check fails CI on inward-boundary violations. Temporal and Docker may evolve without leaking SDK types into policy code.
