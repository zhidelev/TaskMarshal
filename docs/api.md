# Control-plane API contract

The interactive OpenAPI document is served at `/docs`. All failures use the redacted error envelope
documented in [architecture](architecture.md), and every response carries `X-Correlation-ID`.

## Versioned Agent configurations

`POST /api/v1/agents/{agent_id}/configurations` appends an immutable configuration version. The
request includes `name`, unique `role_eligibility` values, `adapter_type`, `provider`, `model`,
`instructions`, `max_concurrency`, `timeout_seconds`, optional `max_cost_usd`, and `created_by`.
Concurrency defaults to 1 and timeout to 1800 seconds. A null cost cap means the configuration adds
no cap beyond the TaskSpecification's mandatory cost limit. Unknown fields, blank/control-bearing
identity text, duplicate roles, booleans or strings in numeric fields, and non-finite costs are
rejected using the redacted validation envelope.

The control plane assigns `id`, the next per-Agent `version`, and `created_at`.
`GET /api/v1/agent-configurations` returns all selectable immutable versions in Agent/version
order. Creating a new version never rewrites an Attempt's configuration reference or snapshot.

## Versioned task specifications

`POST /api/v1/tasks/{work_id}/specifications` appends an immutable version. The request owns these
fields: `repository_id`, `base_revision`, `goal`, `acceptance_criteria`,
`verification_commands`, `constraints`, `actor_configuration_id`,
`reviewer_configuration_id`, `limits`, `required_secret_refs`, `sandbox_policy`,
`dependency_ids`, and `authored_by`. Unknown fields are rejected. IDs, version, author timestamp,
and canonical content digest are generated or assigned by the control plane and appear only in the
response.

The referenced repository and dependencies must belong to the Task's Project. Referenced agent
configurations and dependencies must exist; self- and duplicate dependencies are rejected. Text
collections contain bounded non-blank entries. Limits use strict numeric types and finite values.
Sandbox writable paths are unique absolute POSIX paths without parent traversal, and external
mutation must be false.

`GET /api/v1/tasks/{work_id}` returns the current specification and ordered immutable history.
`GET /api/v1/tasks/{work_id}/readiness` evaluates the current version and returns:

```json
{
  "work_id": "uuid",
  "ready": false,
  "satisfied": 9,
  "total": 11,
  "requirements": [
    {
      "code": "dependencies.completed",
      "satisfied": false,
      "remediation": "Complete or remove each logical task dependency before starting."
    }
  ]
}
```

The actual response contains all 11 requirements, including satisfied entries. Starting an attempt
re-evaluates this same gate and returns HTTP 409 `task.not_ready` with every failed requirement if
any policy is false.
