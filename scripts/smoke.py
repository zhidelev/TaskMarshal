from __future__ import annotations

import json
import os
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE_URL = os.getenv("TASKMARSHAL_API_URL", "http://localhost:8000")


def call(
    path: str, body: dict[str, Any] | None = None, *, expected_status: int | None = None
) -> dict[str, Any]:
    correlation_id = str(uuid4())
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Correlation-ID": correlation_id},
        method="POST" if body is not None else "GET",
    )
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    except (URLError, TimeoutError):
        raise RuntimeError(f"Request failed; correlation_id={correlation_id}") from None
    with response:
        if (expected_status is not None and response.status != expected_status) or (
            expected_status is None and response.status >= 400
        ):
            # Never copy an untrusted server/proxy response body into CI logs.
            raise RuntimeError(
                f"Unexpected HTTP {response.status}; correlation_id={correlation_id}"
            )
        try:
            payload: object = json.load(response)
        except (ValueError, UnicodeError):
            raise RuntimeError(f"Invalid JSON; correlation_id={correlation_id}") from None
        if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
            raise RuntimeError(f"Invalid JSON object; correlation_id={correlation_id}")
        return cast(dict[str, Any], payload)


def main() -> None:
    suffix = uuid4().hex[:8]
    assert call("/health/ready")["status"] == "ready"
    project = call("/api/v1/projects", {"name": f"Smoke {suffix}", "description": "CI"})
    unready = call("/api/v1/tasks", {"project_id": project["id"], "title": "Unready smoke task"})
    rejected = call(f"/api/v1/tasks/{unready['id']}/attempts", {}, expected_status=409)
    assert rejected["error"]["code"] == "task.not_ready"
    assert rejected["error"]["correlation_id"]
    unchanged = call(f"/api/v1/tasks/{unready['id']}")
    assert unchanged["task"]["status"] == "draft" and unchanged["attempts"] == []
    repository = call(
        "/api/v1/repositories",
        {
            "project_id": project["id"],
            "name": "repo",
            "url": "https://example.test/repo.git",
            "access_validated": True,
            "available_secret_refs": [],
        },
    )
    agent = call("/api/v1/agents", {"name": f"Smoke actor {suffix}", "description": "CI"})
    configuration = call(
        f"/api/v1/agents/{agent['id']}/configurations",
        {
            "name": "Smoke actor/reviewer",
            "role_eligibility": ["actor", "reviewer"],
            "adapter_type": "manual",
            "provider": "manual",
            "model": "manual",
            "instructions": "Manually driven smoke attempt",
            "created_by": "smoke",
        },
    )
    task = call("/api/v1/tasks", {"project_id": project["id"], "title": "Smoke foundation"})
    specification = call(
        f"/api/v1/tasks/{task['id']}/specifications",
        {
            "repository_id": repository["id"],
            "base_revision": "0123456789abcdef",
            "goal": "Pass the clean-environment smoke test",
            "acceptance_criteria": ["Attempt starts"],
            "verification_commands": ["make smoke"],
            "constraints": [],
            "actor_configuration_id": configuration["id"],
            "reviewer_configuration_id": configuration["id"],
            "limits": {"timeout_seconds": 60, "max_tokens": 100, "max_cost_usd": 0},
            "required_secret_refs": [],
            "sandbox_policy": {
                "network": "none",
                "writable_paths": ["/workspace"],
                "allow_external_mutation": False,
            },
            "dependency_ids": [],
            "authored_by": "smoke",
        },
    )
    assert specification["version"] == 1
    gate = call(f"/api/v1/tasks/{task['id']}/readiness")
    assert gate["ready"] is True, gate
    attempt = call(f"/api/v1/tasks/{task['id']}/attempts", {})
    assert attempt["work_id"] == task["id"] and attempt["id"] != task["id"]
    print(f"Smoke passed: work_id={task['id']} attempt_id={attempt['id']}")


if __name__ == "__main__":
    main()
