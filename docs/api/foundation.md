# Foundation API

Generated and interactive OpenAPI is available at `/docs`; the raw schema is `/openapi.json`. All resources are under `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST/GET | `/projects` | Create/list projects |
| POST/GET | `/repositories` | Create/list repository configurations |
| POST/GET | `/agents` | Create/list stable agents |
| POST | `/agents/{id}/configurations` | Append an immutable configuration version |
| GET | `/agent-configurations` | List selectable versions |
| POST/GET | `/tasks` | Create/list logical tasks |
| GET | `/tasks/{work_id}` | Read task, current/history specifications, and attempts |
| POST | `/tasks/{work_id}/specifications` | Append an immutable authoritative version |
| GET | `/tasks/{work_id}/readiness` | Evaluate and return the deterministic checklist |
| POST | `/tasks/{work_id}/attempts` | Re-evaluate readiness and manually start an attempt |

An unready start returns HTTP 409 with code `task.not_ready`; `details` contains every failed readiness requirement. Constraint conflicts return `persistence.constraint_violation`. Credentials are represented only by references such as `vault://github/taskmarshal`.
