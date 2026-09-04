from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from taskmarshal.api.schemas import AgentConfigurationCreate


def valid_command() -> dict[str, object]:
    return {
        "name": "Default actor/reviewer",
        "role_eligibility": ["actor", "reviewer"],
        "adapter_type": "pydantic_ai",
        "provider": "openai",
        "model": "openai:test",
        "instructions": "Return only structured results",
        "created_by": "operator",
    }


def test_agent_configuration_has_safe_defaults_and_explicit_cost_policy() -> None:
    configuration = AgentConfigurationCreate.model_validate(valid_command())

    assert configuration.name == "Default actor/reviewer"
    assert configuration.max_concurrency == 1
    assert configuration.timeout_seconds == 1800
    assert configuration.max_cost_usd is None


@pytest.mark.parametrize("cost", [None, 0, 1, 1.5])
def test_cost_policy_accepts_null_or_finite_json_numbers(cost: int | float | None) -> None:
    command = valid_command()
    command["max_cost_usd"] = cost

    assert AgentConfigurationCreate.model_validate(command).max_cost_usd == cost


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "  "),
        ("role_eligibility", ["actor", "actor"]),
        ("max_concurrency", True),
        ("timeout_seconds", "1800"),
        ("max_cost_usd", True),
        ("max_cost_usd", "1"),
        ("max_cost_usd", float("inf")),
        ("instructions", "\x00"),
    ],
)
def test_invalid_agent_configuration_fails_closed(field: str, value: object) -> None:
    command = deepcopy(valid_command())
    command[field] = value

    with pytest.raises(ValidationError):
        AgentConfigurationCreate.model_validate(command)


def test_unknown_agent_configuration_fields_are_rejected() -> None:
    command = valid_command()
    command["api_key"] = "must-not-be-stored"

    with pytest.raises(ValidationError) as error:
        AgentConfigurationCreate.model_validate(command)

    assert error.value.errors()[0]["type"] == "extra_forbidden"
