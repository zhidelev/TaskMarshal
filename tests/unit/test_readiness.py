from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from taskmarshal.domain.readiness import DEFAULT_POLICIES, ReadinessContext, evaluate_readiness


def context(**overrides: object) -> ReadinessContext:
    values: dict[str, object] = {
        "work_id": uuid4(),
        "task_project_id": "project-1",
        "repository": {
            "project_id": "project-1",
            "url": "https://example.test/repo.git",
            "validated_at": datetime.now(UTC),
        },
        "specification": {
            "base_revision": "abc123",
            "goal": "Ship the gate",
            "acceptance_criteria": ["It fails closed"],
            "verification_commands": ["pytest"],
            "limits": {
                "timeout_seconds": 60,
                "max_tokens": 10,
                "max_cost_usd": 1.0,
            },
            "required_secret_refs": ["vault://git"],
            "sandbox_policy": {
                "network": "none",
                "writable_paths": ["/workspace"],
                "allow_external_mutation": False,
            },
            "dependency_ids": ["dependency-1"],
        },
        "actor_configuration": {"role_eligibility": ["actor"]},
        "reviewer_configuration": {"role_eligibility": ["reviewer"]},
        "available_secret_refs": frozenset({"vault://git"}),
        "dependency_statuses": ["completed"],
    }
    values.update(overrides)
    return ReadinessContext(**values)  # type: ignore[arg-type]


def specification(**overrides: object) -> dict[str, object]:
    value = deepcopy(dict(context().specification or {}))
    value.update(overrides)
    return value


def test_complete_context_is_ready_deterministic_and_individually_auditable() -> None:
    readiness_context = context()

    first = evaluate_readiness(readiness_context)
    second = evaluate_readiness(readiness_context)

    assert first == second
    assert first.ready
    assert first.satisfied_count == len(first.requirements) == 11
    assert len({item.code for item in first.requirements}) == len(first.requirements)
    assert all(item.remediation.strip() for item in first.requirements)


@pytest.mark.parametrize(
    ("code", "overrides"),
    [
        ("repository.validated", {"repository": None}),
        ("repository.validated", {"task_project_id": "different-project"}),
        ("base_revision.present", {"specification": specification(base_revision="  ")}),
        ("goal.present", {"specification": specification(goal="\t")}),
        (
            "acceptance_criteria.present",
            {"specification": specification(acceptance_criteria=[""])},
        ),
        ("verification.present", {"specification": specification(verification_commands=[])}),
        ("actor.configured", {"actor_configuration": {"role_eligibility": ["reviewer"]}}),
        ("reviewer.configured", {"reviewer_configuration": {"role_eligibility": ["actor"]}}),
        (
            "limits.present",
            {"specification": specification(limits={"timeout_seconds": 60})},
        ),
        ("secrets.available", {"available_secret_refs": frozenset()}),
        (
            "sandbox_policy.present",
            {
                "specification": specification(
                    sandbox_policy={
                        "network": "none",
                        "writable_paths": ["/workspace/../host"],
                        "allow_external_mutation": False,
                    }
                )
            },
        ),
        ("dependencies.completed", {"dependency_statuses": ["in_progress"]}),
    ],
)
def test_each_requirement_fails_closed_with_a_stable_code(
    code: str, overrides: dict[str, object]
) -> None:
    report = evaluate_readiness(context(**overrides))

    failure = next(item for item in report.requirements if item.code == code)
    assert not report.ready
    assert not failure.satisfied
    assert failure.remediation


def test_missing_specification_returns_every_failed_requirement() -> None:
    missing_context = context(
        repository=None,
        specification=None,
        actor_configuration=None,
        reviewer_configuration=None,
        available_secret_refs=frozenset(),
        dependency_statuses=[],
    )

    report = evaluate_readiness(missing_context)

    assert not report.ready
    assert report.satisfied_count == 0
    assert [item.code for item in report.requirements] == [
        policy.evaluate(missing_context).code for policy in DEFAULT_POLICIES
    ]
    assert all(not item.satisfied and item.remediation for item in report.requirements)


@pytest.mark.parametrize(
    "limits",
    [
        {"timeout_seconds": True, "max_tokens": 10, "max_cost_usd": 1},
        {"timeout_seconds": 0, "max_tokens": 10, "max_cost_usd": 1},
        {"timeout_seconds": 60, "max_tokens": False, "max_cost_usd": 1},
        {"timeout_seconds": 60, "max_tokens": 10, "max_cost_usd": float("inf")},
    ],
)
def test_malformed_limits_never_satisfy_readiness(limits: dict[str, object]) -> None:
    report = evaluate_readiness(context(specification=specification(limits=limits)))

    assert not next(item for item in report.requirements if item.code == "limits.present").satisfied


def test_dependency_shape_and_status_count_must_match() -> None:
    malformed = specification(dependency_ids=["dependency-1", "dependency-1"])

    report = evaluate_readiness(
        context(specification=malformed, dependency_statuses=["completed", "completed"])
    )

    failure = next(item for item in report.requirements if item.code == "dependencies.completed")
    assert not failure.satisfied
