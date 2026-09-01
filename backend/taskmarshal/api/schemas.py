from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    timeout_seconds: int = Field(ge=1, le=86400)
    max_tokens: int = Field(ge=1)
    max_cost_usd: float = Field(ge=0)


class SandboxPolicy(BaseModel):
    network: Literal["none", "allowlist"] = "none"
    writable_paths: list[str] = Field(default_factory=lambda: ["/workspace"])
    allow_external_mutation: Literal[False] = False


class TaskSpecificationCreate(BaseModel):
    repository_id: str
    base_revision: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1, max_length=50000)
    acceptance_criteria: list[str] = Field(min_length=1)
    verification_commands: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    actor_configuration_id: str
    reviewer_configuration_id: str
    limits: Limits
    required_secret_refs: list[str] = Field(default_factory=list)
    sandbox_policy: SandboxPolicy
    dependency_ids: list[str] = Field(default_factory=list)
    authored_by: str = Field(min_length=1, max_length=200)

    @field_validator("base_revision", "goal", "authored_by")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("value contains a null byte")
        return value


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


class ErrorEnvelope(BaseModel):
    error: ErrorBody
