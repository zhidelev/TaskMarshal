from __future__ import annotations

import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient


def test_correlation_id_is_propagated_to_errors_headers_and_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    correlation_id = "89e6b1da-79a7-46b4-b587-2a3c1239d347"

    with caplog.at_level(logging.INFO):
        created = client.post(
            "/api/v1/projects",
            json={"name": "Correlated project", "description": ""},
            headers={"X-Correlation-ID": correlation_id},
        )
        response = client.get(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000000",
            headers={"X-Correlation-ID": correlation_id},
        )

    assert created.status_code == 201
    assert created.headers["X-Correlation-ID"] == correlation_id
    assert response.status_code == 404
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.json()["error"]["correlation_id"] == correlation_id
    assert any(
        record.name == "taskmarshal.operations"
        and getattr(record, "correlation_id", None) == correlation_id
        for record in caplog.records
    )
    assert any(
        record.name == "taskmarshal.requests"
        and getattr(record, "correlation_id", None) == correlation_id
        for record in caplog.records
    )


@pytest.mark.parametrize(
    ("path", "payload", "sentinel"),
    [
        (
            "/api/v1/repositories",
            {
                "name": "repo",
                "url": "https://example.test/repo.git",
                "credential_ref": "credential-value-must-not-escape",
            },
            "credential-value-must-not-escape",
        ),
        (
            "/api/v1/agents/example/configurations",
            {
                "role_eligibility": ["actor"],
                "model": "test:model",
                "instructions": "sensitive-instructions-must-not-escape",
                "created_by": "test",
            },
            "sensitive-instructions-must-not-escape",
        ),
    ],
)
def test_validation_errors_redact_request_values(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    path: str,
    payload: dict[str, object],
    sentinel: str,
) -> None:
    with caplog.at_level(logging.INFO):
        response = client.post(
            path,
            json=payload,
            headers={"X-Correlation-ID": "untrusted-correlation-value"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request.validation_failed"
    assert sentinel not in response.text
    assert sentinel not in caplog.text
    assert "input" not in response.text
    assert response.headers["X-Correlation-ID"] == body["error"]["correlation_id"]
    assert UUID(body["error"]["correlation_id"])
