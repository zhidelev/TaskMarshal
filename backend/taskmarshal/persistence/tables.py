from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Project(Timestamped, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Repository(Timestamped, Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2048))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    credential_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    available_secret_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "name"),)


class Agent(Timestamped, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    configurations: Mapped[list[AgentConfiguration]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", order_by="AgentConfiguration.version"
    )


class AgentConfiguration(Base):
    __tablename__ = "agent_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), server_default="Legacy configuration")
    version: Mapped[int] = mapped_column(Integer)
    role_eligibility: Mapped[list[str]] = mapped_column(JSON)
    adapter_type: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(300))
    instructions: Mapped[str] = mapped_column(Text)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    max_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    agent: Mapped[Agent] = relationship(back_populates="configurations")

    __table_args__ = (
        UniqueConstraint("agent_id", "version"),
        CheckConstraint("version > 0", name="ck_agent_configuration_version_positive"),
    )


class Task(Timestamped, Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    ownership_epoch: Mapped[int] = mapped_column(Integer, default=0)
    current_specification_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    specifications: Mapped[list[TaskSpecification]] = relationship(
        back_populates="task",
        foreign_keys="TaskSpecification.task_id",
        cascade="all, delete-orphan",
        order_by="TaskSpecification.version",
    )
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Attempt.started_at"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["current_specification_id", "id"],
            ["task_specifications.id", "task_specifications.task_id"],
            name="fk_tasks_current_specification_work",
            use_alter=True,
        ),
        CheckConstraint("ownership_epoch >= 0", name="ck_task_epoch_nonnegative"),
    )


class TaskSpecification(Base):
    __tablename__ = "task_specifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    base_revision: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON)
    verification_commands: Mapped[list[str]] = mapped_column(JSON)
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list)
    actor_configuration_id: Mapped[str] = mapped_column(ForeignKey("agent_configurations.id"))
    reviewer_configuration_id: Mapped[str] = mapped_column(ForeignKey("agent_configurations.id"))
    limits: Mapped[dict[str, Any]] = mapped_column(JSON)
    required_secret_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    sandbox_policy: Mapped[dict[str, Any]] = mapped_column(JSON)
    dependency_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    authored_by: Mapped[str] = mapped_column(String(200))
    authored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    task: Mapped[Task] = relationship(back_populates="specifications", foreign_keys=[task_id])

    __table_args__ = (
        UniqueConstraint("task_id", "version"),
        UniqueConstraint("id", "task_id", name="uq_task_specification_identity_work"),
        UniqueConstraint(
            "id",
            "task_id",
            "actor_configuration_id",
            "content_hash",
            name="uq_task_specification_input_identity",
        ),
        CheckConstraint("version > 0", name="ck_task_specification_version_positive"),
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    task_specification_id: Mapped[str] = mapped_column(String(36))
    agent_configuration_id: Mapped[str] = mapped_column(ForeignKey("agent_configurations.id"))
    input_state_id: Mapped[str] = mapped_column(String(64))
    ownership_epoch: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="starting")
    configuration_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    actor_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task: Mapped[Task] = relationship(back_populates="attempts")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["task_specification_id", "work_id", "agent_configuration_id", "input_state_id"],
            [
                "task_specifications.id",
                "task_specifications.task_id",
                "task_specifications.actor_configuration_id",
                "task_specifications.content_hash",
            ],
            name="fk_attempt_input_identity",
        ),
        UniqueConstraint("id", "work_id", name="uq_attempt_identity_work"),
        UniqueConstraint("work_id", "ownership_epoch", name="uq_attempt_work_epoch"),
        CheckConstraint("ownership_epoch > 0", name="ck_attempt_epoch_positive"),
        CheckConstraint("id <> work_id", name="ck_attempt_distinct_identity"),
        Index("ix_attempts_work_started", "work_id", "started_at"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(100))
    uri: Mapped[str] = mapped_column(String(2048))
    digest: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempt: Mapped[Attempt] = relationship(back_populates="artifacts")
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(100))
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    artifact: Mapped[Artifact] = relationship(back_populates="evidence")


class DomainEvent(Base):
    __tablename__ = "domain_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(200))
    work_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    reason_code: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
