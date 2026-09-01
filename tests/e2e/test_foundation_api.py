from __future__ import annotations

from fastapi.testclient import TestClient


def create_project(client: TestClient, name: str = "Control plane") -> dict[str, object]:
    response = client.post("/api/v1/projects", json={"name": name, "description": "Test"})
    assert response.status_code == 201, response.text
    return response.json()


def create_agent_configuration(client: TestClient) -> dict[str, object]:
    agent = client.post(
        "/api/v1/agents", json={"name": "Generalist", "description": "Actor/reviewer"}
    ).json()
    response = client.post(
        f"/api/v1/agents/{agent['id']}/configurations",
        json={
            "role_eligibility": ["actor", "reviewer"],
            "adapter_type": "pydantic_ai",
            "provider": "test",
            "model": "test:model",
            "instructions": "Work carefully",
            "max_concurrency": 1,
            "timeout_seconds": 60,
            "max_cost_usd": 1,
            "created_by": "test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_milestone_scenario_creates_ready_task_and_distinct_attempt(client: TestClient) -> None:
    project = create_project(client)
    repository_response = client.post(
        "/api/v1/repositories",
        json={
            "project_id": project["id"],
            "name": "Repo",
            "url": "https://example.test/repo.git",
            "default_branch": "main",
            "available_secret_refs": ["vault://git"],
            "access_validated": True,
        },
    )
    assert repository_response.status_code == 201, repository_response.text
    repository = repository_response.json()
    configuration = create_agent_configuration(client)
    task_response = client.post(
        "/api/v1/tasks", json={"project_id": project["id"], "title": "Versioned work"}
    )
    assert task_response.status_code == 201, task_response.text
    task = task_response.json()
    specification_response = client.post(
        f"/api/v1/tasks/{task['id']}/specifications",
        json={
            "repository_id": repository["id"],
            "base_revision": "0123456789abcdef",
            "goal": "Prove the foundation flow",
            "acceptance_criteria": ["The attempt starts"],
            "verification_commands": ["pytest"],
            "constraints": ["No external mutation"],
            "actor_configuration_id": configuration["id"],
            "reviewer_configuration_id": configuration["id"],
            "limits": {"timeout_seconds": 60, "max_tokens": 1000, "max_cost_usd": 1},
            "required_secret_refs": ["vault://git"],
            "sandbox_policy": {
                "network": "none",
                "writable_paths": ["/workspace"],
                "allow_external_mutation": False,
            },
            "dependency_ids": [],
            "authored_by": "test",
        },
    )
    assert specification_response.status_code == 201, specification_response.text
    specification = specification_response.json()
    assert specification["version"] == 1

    gate = client.get(f"/api/v1/tasks/{task['id']}/readiness")
    assert gate.status_code == 200, gate.text
    assert gate.json()["ready"] is True
    assert gate.json()["satisfied"] == gate.json()["total"]

    started = client.post(f"/api/v1/tasks/{task['id']}/attempts")
    assert started.status_code == 201, started.text
    attempt = started.json()
    assert attempt["id"] != task["id"]
    assert attempt["work_id"] == task["id"]
    assert attempt["input_state_id"] == specification["content_hash"]

    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["task"]["status"] == "in_progress"
    assert len(detail["attempts"]) == 1

    duplicate = client.post(f"/api/v1/tasks/{task['id']}/attempts")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "agent.concurrency_exhausted"
    assert len(client.get(f"/api/v1/tasks/{task['id']}").json()["attempts"]) == 1


def test_unready_task_start_fails_closed_with_stable_requirements(client: TestClient) -> None:
    project = create_project(client, "Negative path")
    task = client.post(
        "/api/v1/tasks", json={"project_id": project["id"], "title": "Not ready"}
    ).json()

    response = client.post(f"/api/v1/tasks/{task['id']}/attempts")

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "task.not_ready"
    assert {detail["code"] for detail in body["details"]} >= {
        "repository.validated",
        "verification.present",
        "sandbox_policy.present",
    }
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["task"]["status"] == "draft"
    assert detail["attempts"] == []
