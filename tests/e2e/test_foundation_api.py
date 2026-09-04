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


def specification_command(specification: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in specification.items()
        if key not in {"id", "task_id", "version", "authored_at", "content_hash"}
    }


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
    spec_command = specification_command(specification)
    spec_command.update(
        actor_configuration_id=second_config.json()["id"],
        goal="Second goal",
        authored_by="editor@example.test",
    )
    second_spec = client.post(f"/api/v1/tasks/{task['id']}/specifications", json=spec_command)
    assert second_spec.status_code == 201
    assert second_spec.json()["authored_by"] == "editor@example.test"
    assert second_spec.json()["authored_at"]
    assert second_spec.json()["content_hash"] != specification["content_hash"]
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

    gate_response = client.get(f"/api/v1/tasks/{task['id']}/readiness")
    assert gate_response.status_code == 200
    gate = gate_response.json()
    assert gate["ready"] is False
    assert gate["satisfied"] == 0
    assert gate["total"] == 11
    expected_codes = [
        "repository.validated",
        "base_revision.present",
        "goal.present",
        "acceptance_criteria.present",
        "verification.present",
        "actor.configured",
        "reviewer.configured",
        "limits.present",
        "secrets.available",
        "sandbox_policy.present",
        "dependencies.completed",
    ]
    assert [item["code"] for item in gate["requirements"]] == expected_codes
    assert all(not item["satisfied"] and item["remediation"] for item in gate["requirements"])

    response = client.post(f"/api/v1/tasks/{task['id']}/attempts")

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "task.not_ready"
    assert [item["code"] for item in body["details"]] == expected_codes
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["task"]["status"] == "draft"
    assert detail["attempts"] == []


def test_authoritative_edit_creates_version_and_rechecks_readiness(client: TestClient) -> None:
    task, first_specification, _configuration = create_ready_task(client)
    first_gate = client.get(f"/api/v1/tasks/{task['id']}/readiness")
    assert first_gate.status_code == 200
    assert first_gate.json()["ready"] is True
    assert client.get(f"/api/v1/tasks/{task['id']}").json()["task"]["status"] == "ready"

    command = specification_command(first_specification)
    command.update(goal="Edited authoritative goal", authored_by="second-author")
    response = client.post(f"/api/v1/tasks/{task['id']}/specifications", json=command)

    assert response.status_code == 201, response.text
    second = response.json()
    assert second["id"] != first_specification["id"]
    assert second["version"] == 2
    assert second["authored_by"] == "second-author"
    assert second["authored_at"]
    assert second["content_hash"] != first_specification["content_hash"]
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["task"]["status"] == "draft"
    assert detail["current_specification"]["id"] == second["id"]
    assert [item["id"] for item in detail["specification_history"]] == [
        first_specification["id"],
        second["id"],
    ]
    reevaluated = client.get(f"/api/v1/tasks/{task['id']}/readiness")
    assert reevaluated.status_code == 200
    assert reevaluated.json()["ready"] is True


def test_specification_rejects_cross_project_repository_and_dependency(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    task, specification, _configuration = create_ready_task(client)
    foreign_project = create_project(client, "Foreign project")
    foreign_repository = client.post(
        "/api/v1/repositories",
        json={
            "project_id": foreign_project["id"],
            "name": "Foreign repo",
            "url": "https://example.test/foreign.git",
            "access_validated": True,
        },
    )
    assert foreign_repository.status_code == 201
    foreign_task = client.post(
        "/api/v1/tasks",
        json={"project_id": foreign_project["id"], "title": "Foreign dependency"},
    )
    assert foreign_task.status_code == 201

    repository_command = specification_command(specification)
    repository_command["repository_id"] = foreign_repository.json()["id"]
    caplog.clear()
    with caplog.at_level(logging.INFO):
        repository_response = client.post(
            f"/api/v1/tasks/{task['id']}/specifications", json=repository_command
        )
    assert repository_response.status_code == 422
    assert repository_response.json()["error"]["code"] == "repository.project_mismatch"
    operations = [record for record in caplog.records if record.name == "taskmarshal.operations"]
    assert [record.getMessage() for record in operations] == [
        "operation.start",
        "operation.failure",
    ]
    assert all(record.work_id == task["id"] for record in operations)
    assert operations[-1].reason_code == "repository.project_mismatch"

    dependency_command = specification_command(specification)
    dependency_command["dependency_ids"] = [foreign_task.json()["id"]]
    dependency_response = client.post(
        f"/api/v1/tasks/{task['id']}/specifications", json=dependency_command
    )
    assert dependency_response.status_code == 422
    assert dependency_response.json()["error"]["code"] == "dependency.project_mismatch"

    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert len(detail["specification_history"]) == 1


def test_specification_rejects_unknown_and_malformed_authoritative_fields(
    client: TestClient,
) -> None:
    task, specification, _configuration = create_ready_task(client)
    command = specification_command(specification)
    sentinel = "credential-value-must-not-escape"
    command["content_hash"] = sentinel
    command["acceptance_criteria"] = ["   "]
    command["limits"] = {"timeout_seconds": True, "max_tokens": 100, "max_cost_usd": 1}
    command["sandbox_policy"] = {
        "network": "none",
        "writable_paths": ["relative/path"],
        "allow_external_mutation": False,
    }

    response = client.post(f"/api/v1/tasks/{task['id']}/specifications", json=command)

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "request.validation_failed"
    assert {tuple(item["location"]) for item in body["details"]} >= {
        ("body", "content_hash"),
        ("body", "acceptance_criteria"),
        ("body", "limits", "timeout_seconds"),
        ("body", "sandbox_policy", "writable_paths"),
    }
    assert sentinel not in response.text
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert len(detail["specification_history"]) == 1
