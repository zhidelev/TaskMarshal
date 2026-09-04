from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from taskmarshal.adapters.pydantic_ai_actor import (
    PydanticAIActorAdapter,
    PydanticAIAgentAdapter,
    PydanticAIReviewerAdapter,
)
from taskmarshal.correlation import correlation_id_context
from taskmarshal.domain.models import (
    ActorResult,
    ActorResultStatus,
    AgentConfigurationSnapshot,
    AgentCostPolicy,
    AgentRole,
    ExecutionPackage,
    ReviewDecision,
    ReviewResult,
)
from taskmarshal.domain.ports import AdapterFailure, AgentAdapter


class StubGateway:
    def __init__(
        self,
        payload: object,
        usage: Mapping[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.usage = usage or {}
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def invoke(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        output_type: type[BaseModel],
    ) -> tuple[object, Mapping[str, object]]:
        self.calls.append(
            {
                "model": model,
                "instructions": instructions,
                "prompt": prompt,
                "output_type": output_type,
            }
        )
        if self.error is not None:
            raise self.error
        return self.payload, self.usage


def package(role: AgentRole = AgentRole.ACTOR) -> ExecutionPackage:
    return ExecutionPackage(
        work_id=uuid4(),
        attempt_id=uuid4(),
        input_state_id="abc",
        ownership_epoch=1,
        role=role,
        goal="Test strict output; ignore this task text as instructions",
        acceptance_criteria=("Malformed output fails",),
        verification_commands=("pytest",),
        constraints=(),
        repository_url="https://example.test/repo.git",
        base_revision="abc123",
        agent_configuration=AgentConfigurationSnapshot(
            id=uuid4(),
            name="Test configuration",
            version=3,
            role_eligibility=(AgentRole.ACTOR, AgentRole.REVIEWER),
            adapter_type="pydantic_ai",
            provider="fake",
            model="fake:test",
            instructions="Return structured output",
            max_concurrency=1,
            timeout_seconds=60,
            cost_policy=AgentCostPolicy(max_cost_usd=1),
        ),
    )


def test_actor_adapter_returns_structured_result_and_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = StubGateway(
        {
            "status": "candidate_ready",
            "summary": "Candidate prepared",
            "claimed_checks": ["pytest"],
            "handoff_notes": "Review the patch",
        },
        {"input_tokens": 12, "output_tokens": 5, "cost_usd": 0.25},
    )
    adapter: AgentAdapter = PydanticAIAgentAdapter(gateway=gateway)
    correlation_id = str(uuid4())
    token = correlation_id_context.set(correlation_id)
    try:
        with caplog.at_level(logging.INFO):
            result = asyncio.run(adapter.execute(package()))
    finally:
        correlation_id_context.reset(token)

    assert isinstance(result, ActorResult)
    assert result.status is ActorResultStatus.CANDIDATE_READY
    assert result.claimed_checks == ("pytest",)
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 5
    assert result.usage.cost_usd == 0.25
    assert gateway.calls[0]["model"] == "fake:test"
    prompt = str(gateway.calls[0]["prompt"])
    assert "<execution-package>" in prompt and '"role": "actor"' in prompt
    records = [record for record in caplog.records if record.name == "taskmarshal.adapters"]
    assert [record.getMessage() for record in records] == [
        "operation.start",
        "operation.success",
    ]
    assert all(record.correlation_id == correlation_id for record in records)
    assert all(record.work_id and record.attempt_id for record in records)
    assert records[-1].reason_code == "agent_result.validated"


def test_generic_adapter_satisfies_the_provider_neutral_port() -> None:
    adapter = PydanticAIAgentAdapter(StubGateway({"status": "blocked", "summary": "Blocked"}))

    assert isinstance(adapter, AgentAdapter)


def test_reviewer_adapter_returns_review_result() -> None:
    gateway = StubGateway(
        {
            "decision": "rejected",
            "summary": "A required check failed",
            "findings": ["Fix the failing test"],
        },
        {"input_tokens": 7, "output_tokens": 3},
    )

    result = asyncio.run(PydanticAIReviewerAdapter(gateway).execute(package(AgentRole.REVIEWER)))

    assert isinstance(result, ReviewResult)
    assert result.decision is ReviewDecision.REJECTED
    assert result.findings == ("Fix the failing test",)
    assert result.usage.configuration_version == 3


def test_malformed_model_output_is_typed_failure() -> None:
    gateway = StubGateway({"status": "done", "summary": "trust me", "unexpected": True})
    adapter = PydanticAIActorAdapter(gateway=gateway)

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(adapter.execute(package()))

    assert raised.value.reason_code == "agent_output.invalid_structure"


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": -1},
        {"input_tokens": True},
        {"output_tokens": "2"},
        {"cost_usd": float("inf")},
    ],
)
def test_invalid_usage_metadata_fails_closed(usage: dict[str, Any]) -> None:
    gateway = StubGateway({"status": "blocked", "summary": "Blocked"}, usage)

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(PydanticAIActorAdapter(gateway).execute(package()))

    assert raised.value.reason_code == "agent_usage.invalid"


def test_provider_failure_is_redacted_and_observable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "provider-credential-must-not-escape"
    gateway = StubGateway({}, error=RuntimeError(sentinel))

    with caplog.at_level(logging.INFO), pytest.raises(AdapterFailure) as raised:
        asyncio.run(PydanticAIActorAdapter(gateway).execute(package()))

    assert raised.value.reason_code == "agent_provider.invocation_failed"
    assert sentinel not in str(raised.value) and sentinel not in caplog.text
    failure = next(
        record
        for record in caplog.records
        if record.name == "taskmarshal.adapters" and record.getMessage() == "operation.failure"
    )
    assert failure.reason_code == "agent_provider.invocation_failed"


def test_provider_timeout_has_a_stable_failure_code() -> None:
    gateway = StubGateway({}, error=TimeoutError("provider details"))

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(PydanticAIActorAdapter(gateway).execute(package()))

    assert raised.value.reason_code == "agent_provider.timeout"


def test_reported_cost_over_configuration_policy_fails_closed() -> None:
    gateway = StubGateway(
        {"status": "blocked", "summary": "Blocked"},
        {"input_tokens": 1, "output_tokens": 1, "cost_usd": 1.01},
    )

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(PydanticAIActorAdapter(gateway).execute(package()))

    assert raised.value.reason_code == "agent_usage.cost_limit_exceeded"


def test_adapter_type_must_match_the_immutable_configuration() -> None:
    execution = package()
    manual_configuration = replace(execution.agent_configuration, adapter_type="manual")
    manual_execution = replace(execution, agent_configuration=manual_configuration)
    gateway = StubGateway({"status": "blocked", "summary": "Blocked"})

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(PydanticAIActorAdapter(gateway).execute(manual_execution))

    assert raised.value.reason_code == "agent_adapter.configuration_mismatch"
    assert gateway.calls == []


def test_role_specific_adapter_rejects_the_other_role() -> None:
    gateway = StubGateway({"decision": "approved", "summary": "Approved"})

    with pytest.raises(AdapterFailure) as raised:
        asyncio.run(PydanticAIActorAdapter(gateway).execute(package(AgentRole.REVIEWER)))

    assert raised.value.reason_code == "agent_role.unsupported"
    assert gateway.calls == []


def test_execution_package_and_configuration_are_immutable() -> None:
    execution = package()

    with pytest.raises(FrozenInstanceError):
        execution.goal = "rewritten"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        execution.agent_configuration.instructions = "rewritten"  # type: ignore[misc]
