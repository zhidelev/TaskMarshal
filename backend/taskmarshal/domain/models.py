from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
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


@dataclass(frozen=True, slots=True)
class ExecutionPackage:
    work_id: UUID
    attempt_id: UUID
    input_state_id: str
    ownership_epoch: int
    goal: str
    acceptance_criteria: tuple[str, ...]
    verification_commands: tuple[str, ...]
    constraints: tuple[str, ...]
    repository_url: str
    base_revision: str
    agent_configuration: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    provider: str
    model: str
    configuration_version: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class ActorResult:
    status: ActorResultStatus
    summary: str
    claimed_checks: tuple[str, ...] = ()
    handoff_notes: str = ""
    usage: UsageMetadata | None = None


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
