from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from taskmarshal.api.schemas import TaskSpecificationCreate


def valid_command() -> dict[str, object]:
    return {
        "repository_id": "00000000-0000-0000-0000-000000000001",
        "base_revision": "abc123",
        "goal": "Deliver deterministic readiness",
        "acceptance_criteria": ["Every requirement is visible"],
        "verification_commands": ["pytest"],
        "constraints": ["Fail closed"],
        "actor_configuration_id": "00000000-0000-0000-0000-000000000002",
        "reviewer_configuration_id": "00000000-0000-0000-0000-000000000003",
        "limits": {"timeout_seconds": 60, "max_tokens": 100, "max_cost_usd": 1.0},
        "required_secret_refs": ["vault://git"],
        "sandbox_policy": {
            "network": "none",
            "writable_paths": ["/workspace"],
            "allow_external_mutation": False,
        },
        "dependency_ids": ["00000000-0000-0000-0000-000000000004"],
        "authored_by": "operator",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("goal", "   "),
        ("acceptance_criteria", [""]),
        (
            "limits",
            {"timeout_seconds": True, "max_tokens": 100, "max_cost_usd": 1.0},
        ),
        (
            "sandbox_policy",
            {
                "network": "none",
                "writable_paths": ["/workspace/../host"],
                "allow_external_mutation": False,
            },
        ),
        (
            "dependency_ids",
            [
                "00000000-0000-0000-0000-000000000004",
                "00000000-0000-0000-0000-000000000004",
            ],
        ),
        ("required_secret_refs", ["vault://git", "vault://git"]),
    ],
)
def test_malformed_authoritative_input_is_rejected(field: str, value: object) -> None:
    command = deepcopy(valid_command())
    command[field] = value

    with pytest.raises(ValidationError):
        TaskSpecificationCreate.model_validate(command)


def test_response_owned_fields_are_rejected() -> None:
    command = valid_command()
    command["content_hash"] = "caller-controlled"

    with pytest.raises(ValidationError) as error:
        TaskSpecificationCreate.model_validate(command)

    assert error.value.errors()[0]["type"] == "extra_forbidden"
