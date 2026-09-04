from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Protocol
from uuid import UUID

from taskmarshal.domain.models import ReadinessReport, ReadinessRequirement


@dataclass(frozen=True, slots=True)
class ReadinessContext:
    work_id: UUID
    task_project_id: str
    repository: Mapping[str, Any] | None
    specification: Mapping[str, Any] | None
    actor_configuration: Mapping[str, Any] | None
    reviewer_configuration: Mapping[str, Any] | None
    available_secret_refs: frozenset[str]
    dependency_statuses: Sequence[str]


class ReadinessPolicy(Protocol):
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement: ...


@dataclass(frozen=True, slots=True)
class RequiredTextPolicy:
    code: str
    key: str
    remediation: str

    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        value = (context.specification or {}).get(self.key)
        satisfied = isinstance(value, str) and bool(value.strip()) and "\x00" not in value
        return ReadinessRequirement(self.code, satisfied, self.remediation)


@dataclass(frozen=True, slots=True)
class RequiredTextListPolicy:
    code: str
    key: str
    remediation: str

    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        value = (context.specification or {}).get(self.key)
        satisfied = (
            isinstance(value, list)
            and bool(value)
            and all(
                isinstance(item, str) and bool(item.strip()) and "\x00" not in item
                for item in value
            )
        )
        return ReadinessRequirement(self.code, satisfied, self.remediation)


class RepositoryPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        repository = context.repository or {}
        url = repository.get("url")
        satisfied = (
            isinstance(url, str)
            and bool(url.strip())
            and not any(character in url for character in ("\n", "\r", "\x00"))
            and isinstance(repository.get("validated_at"), datetime)
            and repository.get("project_id") == context.task_project_id
        )
        return ReadinessRequirement(
            "repository.validated",
            satisfied,
            (
                "Select a repository from this task's project and validate access from the "
                "control plane."
            ),
        )


class ActorPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        configured_roles = (context.actor_configuration or {}).get("role_eligibility")
        roles = set(configured_roles) if isinstance(configured_roles, list) else set()
        return ReadinessRequirement(
            "actor.configured",
            "actor" in roles,
            "Select an immutable agent configuration eligible for the actor role.",
        )


class ReviewerPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        configured_roles = (context.reviewer_configuration or {}).get("role_eligibility")
        roles = set(configured_roles) if isinstance(configured_roles, list) else set()
        return ReadinessRequirement(
            "reviewer.configured",
            "reviewer" in roles,
            "Select an immutable agent configuration eligible for the reviewer role.",
        )


class SecretsPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        configured = (context.specification or {}).get("required_secret_refs")
        if isinstance(configured, list):
            valid_references = all(
                isinstance(item, str) and bool(item.strip()) for item in configured
            ) and len(configured) == len(set(configured))
            required = set(configured) if valid_references else set()
        else:
            valid_references = False
            required = set()
        missing = required - context.available_secret_refs
        return ReadinessRequirement(
            "secrets.available",
            valid_references and not missing,
            (
                "Register every required credential reference in the control plane; "
                "never put values in task content."
            ),
        )


class DependenciesPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        dependency_ids = (context.specification or {}).get("dependency_ids")
        if isinstance(dependency_ids, list):
            valid_dependencies = all(
                isinstance(item, str) and bool(item.strip()) for item in dependency_ids
            ) and len(dependency_ids) == len(set(dependency_ids))
            count_matches = len(dependency_ids) == len(context.dependency_statuses)
        else:
            valid_dependencies = False
            count_matches = False
        satisfied = (
            valid_dependencies
            and count_matches
            and all(status == "completed" for status in context.dependency_statuses)
        )
        return ReadinessRequirement(
            "dependencies.completed",
            satisfied,
            "Complete or remove each logical task dependency before starting.",
        )


class LimitsPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        limits = (context.specification or {}).get("limits")
        timeout = limits.get("timeout_seconds") if isinstance(limits, Mapping) else None
        max_tokens = limits.get("max_tokens") if isinstance(limits, Mapping) else None
        max_cost = limits.get("max_cost_usd") if isinstance(limits, Mapping) else None
        satisfied = (
            isinstance(timeout, int)
            and not isinstance(timeout, bool)
            and 1 <= timeout <= 86_400
            and isinstance(max_tokens, int)
            and not isinstance(max_tokens, bool)
            and max_tokens >= 1
            and isinstance(max_cost, int | float)
            and not isinstance(max_cost, bool)
            and math.isfinite(max_cost)
            and max_cost >= 0
        )
        return ReadinessRequirement(
            "limits.present",
            satisfied,
            "Set valid time, token, and finite non-negative cost limits.",
        )


class SandboxPolicy:
    def evaluate(self, context: ReadinessContext) -> ReadinessRequirement:
        policy = (context.specification or {}).get("sandbox_policy")
        network = policy.get("network") if isinstance(policy, Mapping) else None
        paths = policy.get("writable_paths") if isinstance(policy, Mapping) else None
        external_mutation = (
            policy.get("allow_external_mutation") if isinstance(policy, Mapping) else None
        )
        valid_paths = (
            isinstance(paths, list)
            and bool(paths)
            and all(
                isinstance(path, str)
                and path.startswith("/")
                and bool(path.strip())
                and not any(character in path for character in ("\n", "\r", "\x00"))
                and ".." not in PurePosixPath(path).parts
                for path in paths
            )
            and len(paths) == len(set(paths))
        )
        satisfied = network in {"none", "allowlist"} and valid_paths and external_mutation is False
        return ReadinessRequirement(
            "sandbox_policy.present",
            satisfied,
            (
                "Select a least-privilege sandbox with absolute writable paths and external "
                "mutation disabled."
            ),
        )


DEFAULT_POLICIES: tuple[ReadinessPolicy, ...] = (
    RepositoryPolicy(),
    RequiredTextPolicy("base_revision.present", "base_revision", "Set an immutable base revision."),
    RequiredTextPolicy("goal.present", "goal", "Describe the intended outcome."),
    RequiredTextListPolicy(
        "acceptance_criteria.present",
        "acceptance_criteria",
        "Add at least one acceptance criterion.",
    ),
    RequiredTextListPolicy(
        "verification.present", "verification_commands", "Add at least one verification command."
    ),
    ActorPolicy(),
    ReviewerPolicy(),
    LimitsPolicy(),
    SecretsPolicy(),
    SandboxPolicy(),
    DependenciesPolicy(),
)


def evaluate_readiness(
    context: ReadinessContext, policies: Sequence[ReadinessPolicy] = DEFAULT_POLICIES
) -> ReadinessReport:
    return ReadinessReport(context.work_id, tuple(policy.evaluate(context) for policy in policies))
