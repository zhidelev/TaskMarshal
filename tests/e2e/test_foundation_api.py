from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from taskmarshal.api.service import ControlPlaneService
from taskmarshal.persistence.tables import Attempt, DomainEvent, Task


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


def create_ready_task(client: TestClient) -> tuple[dict, dict, dict]:
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
    return task, specification, configuration


def test_milestone_scenario_creates_ready_task_and_distinct_attempt(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    task, specification, _configuration = create_ready_task(client)

    gate = client.get(f"/api/v1/tasks/{task['id']}/readiness")
    assert gate.status_code == 200, gate.text
    assert gate.json()["ready"] is True
    assert gate.json()["satisfied"] == gate.json()["total"]

    caplog.clear()
    with caplog.at_level(logging.INFO):
        started = client.post(f"/api/v1/tasks/{task['id']}/attempts")
    assert started.status_code == 201, started.text
    attempt = started.json()
    assert attempt["id"] != task["id"]
    assert attempt["work_id"] == task["id"]
    assert attempt["input_state_id"] == specification["content_hash"]
    assert attempt["ownership_epoch"] == 1
    operations = [record for record in caplog.records if record.name == "taskmarshal.operations"]
    assert [record.getMessage() for record in operations] == [
        "operation.start",
        "operation.success",
    ]
    assert all(
        record.work_id == task["id"] and record.attempt_id == attempt["id"] for record in operations
    )
    assert all(
        record.correlation_id == started.headers["X-Correlation-ID"] for record in operations
    )
    assert operations[-1].duration_ms >= 0

    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["task"]["status"] == "in_progress"
    assert len(detail["attempts"]) == 1

    duplicate = client.post(f"/api/v1/tasks/{task['id']}/attempts")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "agent.concurrency_exhausted"
    assert len(client.get(f"/api/v1/tasks/{task['id']}").json()["attempts"]) == 1


def test_new_versions_do_not_rewrite_attempt_inputs_or_history(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    task, specification, configuration = create_ready_task(client)
    first = client.post(f"/api/v1/tasks/{task['id']}/attempts")
    assert first.status_code == 201
    with session_factory() as session:
        attempt = session.get(Attempt, first.json()["id"])
        assert attempt is not None
        original_snapshot = attempt.configuration_snapshot
        original_events = list(session.scalars(select(DomainEvent.id)))
    config_command = {
        key: value
        for key, value in configuration.items()
        if key not in {"id", "agent_id", "version", "created_at"}
    }
    config_command["instructions"] = "Second version"
    second_config = client.post(
        f"/api/v1/agents/{configuration['agent_id']}/configurations", json=config_command
    )
    assert second_config.status_code == 201
    assert second_config.json()["version"] == 2
    spec_command = {
        key: value
        for key, value in specification.items()
        if key not in {"id", "task_id", "version", "authored_at", "content_hash"}
    }
    spec_command.update(actor_configuration_id=second_config.json()["id"], goal="Second goal")
    second_spec = client.post(f"/api/v1/tasks/{task['id']}/specifications", json=spec_command)
    assert second_spec.status_code == 201
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert [item["version"] for item in detail["specification_history"]] == [1, 2]
    assert detail["current_specification"]["id"] == second_spec.json()["id"]
    assert detail["attempts"][0] == first.json()
    with session_factory() as session:
        attempt = session.get(Attempt, first.json()["id"])
        assert attempt is not None and attempt.configuration_snapshot == original_snapshot
        assert set(original_events) < set(session.scalars(select(DomainEvent.id)))


def test_attempt_and_epoch_roll_back_if_event_persistence_fails(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    task, _specification, _configuration = create_ready_task(client)
    original = ControlPlaneService._event
    sentinel = "sensitive-instructions-must-not-escape"

    def fail_event(
        service: ControlPlaneService, event_type: str, *args: object, **kwargs: object
    ) -> None:
        if event_type == "attempt.started":
            raise IntegrityError("INSERT", {"instructions": sentinel}, Exception(sentinel))
        original(service, event_type, *args, **kwargs)

    monkeypatch.setattr(ControlPlaneService, "_event", fail_event)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = client.post(f"/api/v1/tasks/{task['id']}/attempts")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "persistence.constraint_violation"
    assert response.json()["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert sentinel not in response.text and sentinel not in caplog.text
    operations = [record for record in caplog.records if record.name == "taskmarshal.operations"]
    assert [record.getMessage() for record in operations] == [
        "operation.start",
        "operation.failure",
    ]
    assert operations[0].attempt_id == operations[1].attempt_id
    assert operations[1].work_id == task["id"]
    assert operations[1].reason_code == "persistence.constraint_violation"
    with session_factory() as session:
        assert list(session.scalars(select(Attempt))) == []
        assert session.scalar(select(Task.ownership_epoch).where(Task.id == task["id"])) == 0
        assert (
            session.scalar(select(DomainEvent).where(DomainEvent.event_type == "attempt.started"))
            is None
        )


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
