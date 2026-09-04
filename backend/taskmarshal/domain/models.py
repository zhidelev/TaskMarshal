from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AttemptStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    CANDIDATE = "candidate"
    BLOCKED = "blocked"
    FAILED = "failed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AgentRole(StrEnum):
    ACTOR = "actor"
    REVIEWER = "reviewer"


class ActorResultStatus(StrEnum):
    CANDIDATE_READY = "candidate_ready"
    BLOCKED = "blocked"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AgentCostPolicy:
    max_cost_usd: float | None

    def __post_init__(self) -> None:
        if self.max_cost_usd is not None and (
            isinstance(self.max_cost_usd, bool)
            or not isinstance(self.max_cost_usd, int | float)
            or not math.isfinite(self.max_cost_usd)
            or self.max_cost_usd < 0
        ):
            raise ValueError("agent cost cap must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class AgentConfigurationSnapshot:
    id: UUID
    name: str
    version: int
    role_eligibility: tuple[AgentRole, ...]
    adapter_type: str
    provider: str
    model: str
    instructions: str
    max_concurrency: int
    timeout_seconds: int
    cost_policy: AgentCostPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.cost_policy, AgentCostPolicy):
            raise ValueError("agent configuration identity and cost policy must be typed")
        required_text = (
            self.name,
            self.adapter_type,
            self.provider,
            self.model,
            self.instructions,
        )
        if any(
            not isinstance(value, str) or not value.strip() or "\x00" in value
            for value in required_text
        ):
            raise ValueError("agent configuration text must be non-blank and contain no nulls")
        if (
            not isinstance(self.role_eligibility, tuple)
            or not self.role_eligibility
            or len(self.role_eligibility) != len(set(self.role_eligibility))
            or not all(isinstance(role, AgentRole) for role in self.role_eligibility)
        ):
            raise ValueError("agent configuration roles must be unique AgentRole values")
        integer_policy = (self.version, self.max_concurrency, self.timeout_seconds)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in integer_policy):
            raise ValueError("agent configuration numeric policy must use integers")
        if self.version < 1 or self.max_concurrency < 1:
            raise ValueError("agent configuration version and concurrency must be positive")
        if not 1 <= self.timeout_seconds <= 86_400:
            raise ValueError("agent configuration timeout is outside the supported range")


@dataclass(frozen=True, slots=True)
class ExecutionPackage:
    work_id: UUID
    attempt_id: UUID
    input_state_id: str
    ownership_epoch: int
    role: AgentRole
    goal: str
    acceptance_criteria: tuple[str, ...]
    verification_commands: tuple[str, ...]
    constraints: tuple[str, ...]
    repository_url: str
    base_revision: str
    agent_configuration: AgentConfigurationSnapshot

    def __post_init__(self) -> None:
        if (
            not isinstance(self.work_id, UUID)
            or not isinstance(self.attempt_id, UUID)
            or not isinstance(self.role, AgentRole)
            or not isinstance(self.agent_configuration, AgentConfigurationSnapshot)
        ):
            raise ValueError("execution identity, role, and configuration must be typed")
        if not all(
            isinstance(values, tuple)
            for values in (
                self.acceptance_criteria,
                self.verification_commands,
                self.constraints,
            )
        ):
            raise ValueError("execution package collections must be immutable tuples")
        if self.work_id == self.attempt_id:
            raise ValueError("work and attempt identities must be distinct")
        if (
            not isinstance(self.ownership_epoch, int)
            or isinstance(self.ownership_epoch, bool)
            or self.ownership_epoch < 1
            or not isinstance(self.input_state_id, str)
            or not self.input_state_id.strip()
        ):
            raise ValueError("execution identity must be complete")
        if self.role not in self.agent_configuration.role_eligibility:
            raise ValueError("agent configuration is not eligible for the requested role")
        text_values = (
            self.goal,
            self.repository_url,
            self.base_revision,
            *self.acceptance_criteria,
            *self.verification_commands,
            *self.constraints,
        )
        if any(
            not isinstance(value, str) or not value.strip() or "\x00" in value
            for value in text_values
        ):
            raise ValueError("execution package contains invalid task text")
        if not self.acceptance_criteria or not self.verification_commands:
            raise ValueError("execution package is missing authoritative task input")


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    provider: str
    model: str
    configuration_version: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider, str)
            or not isinstance(self.model, str)
            or not self.provider.strip()
            or not self.model.strip()
            or "\x00" in self.provider
            or "\x00" in self.model
            or not isinstance(self.configuration_version, int)
            or isinstance(self.configuration_version, bool)
            or self.configuration_version < 1
        ):
            raise ValueError("usage identity must be complete")
        if (
            isinstance(self.input_tokens, bool)
            or isinstance(self.output_tokens, bool)
            or not isinstance(self.input_tokens, int)
            or not isinstance(self.output_tokens, int)
            or self.input_tokens < 0
            or self.output_tokens < 0
        ):
            raise ValueError("token usage cannot be negative")
        if self.cost_usd is not None and (
            isinstance(self.cost_usd, bool)
            or not isinstance(self.cost_usd, int | float)
            or not math.isfinite(self.cost_usd)
            or self.cost_usd < 0
        ):
            raise ValueError("usage cost must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ActorResult:
    status: ActorResultStatus
    summary: str
    usage: UsageMetadata
    claimed_checks: tuple[str, ...] = ()
    handoff_notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, ActorResultStatus) or not isinstance(
            self.usage, UsageMetadata
        ):
            raise ValueError("actor result status and usage must be typed")
        if (
            not isinstance(self.summary, str)
            or not isinstance(self.handoff_notes, str)
            or not self.summary.strip()
            or "\x00" in self.summary
            or "\x00" in self.handoff_notes
        ):
            raise ValueError("actor result summary must be valid")
        if not isinstance(self.claimed_checks, tuple) or any(
            not isinstance(check, str) or not check.strip() or "\x00" in check
            for check in self.claimed_checks
        ):
            raise ValueError("actor claimed checks must be valid")


@dataclass(frozen=True, slots=True)
class ReviewResult:
    decision: ReviewDecision
    summary: str
    usage: UsageMetadata
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ReviewDecision) or not isinstance(
            self.usage, UsageMetadata
        ):
            raise ValueError("review decision and usage must be typed")
        if not isinstance(self.summary, str) or not self.summary.strip() or "\x00" in self.summary:
            raise ValueError("review result summary must be valid")
        if not isinstance(self.findings, tuple) or any(
            not isinstance(finding, str) or not finding.strip() or "\x00" in finding
            for finding in self.findings
        ):
            raise ValueError("review findings must be valid")


AgentResult = ActorResult | ReviewResult


@dataclass(frozen=True, slots=True)
class ReadinessRequirement:
    code: str
    satisfied: bool
    remediation: str


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    work_id: UUID
    requirements: tuple[ReadinessRequirement, ...]

    @property
    def ready(self) -> bool:
        return all(requirement.satisfied for requirement in self.requirements)

    @property
    def satisfied_count(self) -> int:
        return sum(requirement.satisfied for requirement in self.requirements)


@dataclass(slots=True)
class AttemptState:
    work_id: UUID
    agent_configuration_id: UUID
    input_state_id: str
    ownership_epoch: int
    id: UUID = field(default_factory=uuid4)
    status: AttemptStatus = AttemptStatus.STARTING
    started_at: datetime = field(default_factory=utc_now)
