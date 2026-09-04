from __future__ import annotations

import math
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class ProjectView(ORMModel):
    id: str
    name: str
    description: str
    created_at: datetime


class RepositoryCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=3, max_length=2048)
    default_branch: str = Field(default="main", min_length=1, max_length=255)
    credential_ref: str | None = Field(default=None, max_length=500)
    available_secret_refs: list[str] = Field(default_factory=list)
    access_validated: bool = False

    @field_validator("url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        if any(character in value for character in ("\n", "\r", "\x00")):
            raise ValueError("repository URL contains control characters")
        allowed = ("https://", "ssh://", "git@", "file://")
        if not value.startswith(allowed):
            raise ValueError("repository URL must use https, ssh, git@, or file")
        return value


class RepositoryView(ORMModel):
    id: str
    project_id: str
    name: str
    url: str
    default_branch: str
    credential_ref: str | None
    available_secret_refs: list[str]
    validated_at: datetime | None


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class AgentView(ORMModel):
    id: str
    name: str
    description: str
    created_at: datetime


class AgentConfigurationCreate(BaseModel):
    role_eligibility: list[Literal["actor", "reviewer"]] = Field(min_length=1)
    adapter_type: Literal["pydantic_ai", "manual"] = "pydantic_ai"
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=50000)
    max_concurrency: int = Field(default=1, ge=1, le=100)
    timeout_seconds: int = Field(default=1800, ge=1, le=86400)
    max_cost_usd: float | None = Field(default=None, ge=0)
    created_by: str = Field(min_length=1, max_length=200)


class AgentConfigurationView(ORMModel):
    id: str
    agent_id: str
    version: int
    role_eligibility: list[str]
    adapter_type: str
    provider: str
    model: str
    instructions: str
    max_concurrency: int
    timeout_seconds: int
    max_cost_usd: float | None
    created_by: str
    created_at: datetime


class TaskCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=500)


class TaskView(ORMModel):
    id: str
    project_id: str
    title: str
    status: str
    ownership_epoch: int
    current_specification_id: str | None
    created_at: datetime


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(ge=1, le=86400, strict=True)
    max_tokens: int = Field(ge=1, strict=True)
    max_cost_usd: int | float = Field(ge=0)

    @field_validator("max_cost_usd", mode="before")
    @classmethod
    def validate_max_cost(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("maximum cost must be an integer or float")
        if not math.isfinite(value):
            raise ValueError("maximum cost must be finite")
        return value


class SandboxPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: Literal["none", "allowlist"] = "none"
    writable_paths: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=lambda: ["/workspace"], min_length=1, max_length=32
    )
    allow_external_mutation: Literal[False] = False

    @field_validator("writable_paths")
    @classmethod
    def validate_writable_paths(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("writable paths must be unique")
        for path in value:
            parsed = PurePosixPath(path)
            if not path.startswith("/") or ".." in parsed.parts:
                raise ValueError("writable paths must be absolute and cannot traverse parents")
            if any(character in path for character in ("\n", "\r", "\x00")):
                raise ValueError("writable path contains control characters")
        return value


class TaskSpecificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_id: str = Field(min_length=1, max_length=36)
    base_revision: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1, max_length=50000)
    acceptance_criteria: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(
        min_length=1, max_length=100
    )
    verification_commands: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(
        min_length=1, max_length=100
    )
    constraints: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(
        default_factory=list, max_length=100
    )
    actor_configuration_id: str = Field(min_length=1, max_length=36)
    reviewer_configuration_id: str = Field(min_length=1, max_length=36)
    limits: Limits
    required_secret_refs: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=100
    )
    sandbox_policy: SandboxPolicy
    dependency_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(
        default_factory=list, max_length=100
    )
    authored_by: str = Field(min_length=1, max_length=200)

    @field_validator("base_revision", "authored_by")
    @classmethod
    def validate_single_line_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must contain non-whitespace text")
        if any(character in value for character in ("\n", "\r", "\x00")):
            raise ValueError("value contains control characters")
        return value

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must contain non-whitespace text")
        if "\x00" in value:
            raise ValueError("value contains a null byte")
        return value

    @field_validator("acceptance_criteria", "verification_commands", "constraints")
    @classmethod
    def validate_text_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("items must contain non-whitespace text")
        if any("\x00" in item for item in value):
            raise ValueError("items cannot contain null bytes")
        return value

    @field_validator("required_secret_refs")
    @classmethod
    def validate_secret_references(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("secret references must contain non-whitespace text")
        if any(character in item for item in value for character in ("\n", "\r", "\x00")):
            raise ValueError("secret references cannot contain control characters")
        if len(value) != len(set(value)):
            raise ValueError("secret references must be unique")
        return value

    @model_validator(mode="after")
    def validate_dependencies(self) -> Self:
        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ValueError("dependencies must be unique")
        return self


class TaskSpecificationView(ORMModel):
    id: str
    task_id: str
    version: int
    repository_id: str
    base_revision: str
    goal: str
    acceptance_criteria: list[str]
    verification_commands: list[str]
    constraints: list[str]
    actor_configuration_id: str
    reviewer_configuration_id: str
    limits: dict[str, Any]
    required_secret_refs: list[str]
    sandbox_policy: dict[str, Any]
    dependency_ids: list[str]
    authored_by: str
    authored_at: datetime
    content_hash: str


class ReadinessRequirementView(BaseModel):
    code: str
    satisfied: bool
    remediation: str


class ReadinessView(BaseModel):
    work_id: str
    ready: bool
    satisfied: int
    total: int
    requirements: list[ReadinessRequirementView]


class AttemptView(ORMModel):
    id: str
    work_id: str
    task_specification_id: str
    agent_configuration_id: str
    input_state_id: str
    ownership_epoch: int
    status: str
    workflow_run_id: str | None
    started_at: datetime
    finished_at: datetime | None


class TaskDetail(BaseModel):
    task: TaskView
    current_specification: TaskSpecificationView | None
    specification_history: list[TaskSpecificationView]
    attempts: list[AttemptView]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
