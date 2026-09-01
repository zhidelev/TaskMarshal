from __future__ import annotations

from uuid import uuid4

from taskmarshal.domain.readiness import ReadinessContext, evaluate_readiness


def context(**overrides: object) -> ReadinessContext:
    values: dict[str, object] = {
        "work_id": uuid4(),
        "repository": {"url": "https://example.test/repo.git", "validated_at": "now"},
        "specification": {
            "base_revision": "abc123",
            "goal": "Ship the gate",
            "acceptance_criteria": ["It fails closed"],
            "verification_commands": ["pytest"],
            "limits": {"max_tokens": 10},
            "required_secret_refs": ["vault://git"],
            "sandbox_policy": {"network": "none"},
        },
        "actor_configuration": {"role_eligibility": ["actor"]},
        "reviewer_configuration": {"role_eligibility": ["reviewer"]},
        "available_secret_refs": frozenset({"vault://git"}),
        "dependency_statuses": ["completed"],
    }
    values.update(overrides)
    return ReadinessContext(**values)  # type: ignore[arg-type]


def test_complete_context_is_ready_and_individually_auditable() -> None:
    report = evaluate_readiness(context())

    assert report.ready
    assert report.satisfied_count == len(report.requirements) == 11
    assert len({item.code for item in report.requirements}) == len(report.requirements)


def test_missing_secret_ref_has_stable_failure_code() -> None:
    report = evaluate_readiness(context(available_secret_refs=frozenset()))

    failure = next(item for item in report.requirements if item.code == "secrets.available")
    assert not report.ready
    assert not failure.satisfied
    assert "credential reference" in failure.remediation
