from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from taskmarshal.adapters.pydantic_ai_actor import PydanticAIActorAdapter
from taskmarshal.domain.models import ExecutionPackage
from taskmarshal.domain.ports import AdapterFailure


class MalformedGateway:
    async def invoke(self, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
        return {"status": "done", "summary": "trust me", "unexpected": True}, {}


def package() -> ExecutionPackage:
    return ExecutionPackage(
        work_id=uuid4(),
        attempt_id=uuid4(),
        input_state_id="abc",
        ownership_epoch=1,
        goal="Test strict output",
        acceptance_criteria=("Malformed output fails",),
        verification_commands=("pytest",),
        constraints=(),
        repository_url="https://example.test/repo.git",
        base_revision="abc123",
        agent_configuration={
            "provider": "fake",
            "model": "fake:test",
            "version": 3,
            "instructions": "Return structured output",
        },
    )


def test_malformed_model_output_is_typed_failure() -> None:
    adapter = PydanticAIActorAdapter(gateway=MalformedGateway())  # type: ignore[arg-type]

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(adapter.execute(package()))

    assert raised.value.reason_code == "agent_output.invalid_structure"
