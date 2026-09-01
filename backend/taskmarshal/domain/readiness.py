from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from taskmarshal.domain.models import ReadinessReport, ReadinessRequirement


@dataclass(frozen=True, slots=True)
class ReadinessContext:
    work_id: UUID
    repository: Mapping[str, Any] | None
    specification: Mapping[str, Any] | None
    actor_configuration: Mapping[str, Any] | None
    reviewer_configuration: Mapping[str, Any] | None
    available_secret_refs: frozenset[str]
    dependency_statuses: Sequence[str]


class ReadinessPolicy(Protocol):
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement: ...


@dataclass(frozen=True, slots=True)
class RequiredValuePolicy:
    code: str
    key: str
    remediation: str

    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        value = (context.specification or {}).get(self.key)
        satisfied = bool(value) and (not isinstance(value, list) or len(value) > 0)
        return ReadinessRequirement(self.code, satisfied, self.remediation)


class RepositoryPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        repository = context.repository or {}
        satisfied = bool(repository.get("url")) and bool(repository.get("validated_at"))
        return ReadinessRequirement(
            "repository.validated",
            satisfied,
            "Configure the repository URL and validate access from the control plane.",
        )


class ActorPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        roles = set((context.actor_configuration or {}).get("role_eligibility", []))
        return ReadinessRequirement(
            "actor.configured",
            "actor" in roles,
            "Select an immutable agent configuration eligible for the actor role.",
        )


class ReviewerPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        roles = set((context.reviewer_configuration or {}).get("role_eligibility", []))
        return ReadinessRequirement(
            "reviewer.configured",
            "reviewer" in roles,
            "Select an immutable agent configuration eligible for the reviewer role.",
        )


class SecretsPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        required = set((context.specification or {}).get("required_secret_refs", []))
        missing = required - context.available_secret_refs
        return ReadinessRequirement(
            "secrets.available",
            not missing,
            (
                "Register every required credential reference in the control plane; "
                "never put values in task content."
            ),
        )


class DependenciesPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        satisfied = all(status == "completed" for status in context.dependency_statuses)
        return ReadinessRequirement(
            "dependencies.completed",
            satisfied,
            "Complete or remove each logical task dependency before starting.",
        )


DEFAULT_POLICIES: tuple[ReadinessPolicy, ...] = (
    RepositoryPolicy(),
    RequiredValuePolicy(
        "base_revision.present", "base_revision", "Set an immutable base revision."
    ),
    RequiredValuePolicy("goal.present", "goal", "Describe the intended outcome."),
    RequiredValuePolicy(
        "acceptance_criteria.present",
        "acceptance_criteria",
        "Add at least one acceptance criterion.",
    ),
    RequiredValuePolicy(
        "verification.present", "verification_commands", "Add at least one verification command."
    ),
    ActorPolicy(),
    ReviewerPolicy(),
    RequiredValuePolicy("limits.present", "limits", "Set time, token, and cost limits."),
    SecretsPolicy(),
    RequiredValuePolicy(
        "sandbox_policy.present", "sandbox_policy", "Select a least-privilege sandbox policy."
    ),
    DependenciesPolicy(),
)


def evaluate_readiness(
    context: ReadinessContext, policies: Sequence[ReadinessPolicy] = DEFAULT_POLICIES
) -> ReadinessReport:
    return ReadinessReport(context.work_id, tuple(policy.evaluate(context) for policy in policies))
