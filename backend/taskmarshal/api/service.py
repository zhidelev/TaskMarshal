from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from taskmarshal.api.errors import DomainError
from taskmarshal.api.schemas import (
    AgentConfigurationCreate,
    AgentCreate,
    ProjectCreate,
    RepositoryCreate,
    TaskCreate,
    TaskSpecificationCreate,
)
from taskmarshal.domain.models import TaskStatus
from taskmarshal.domain.readiness import ReadinessContext, evaluate_readiness
from taskmarshal.domain.transitions import InvalidTransition, start_attempt
from taskmarshal.persistence.tables import (
    Agent,
    AgentConfiguration,
    Attempt,
    DomainEvent,
    Project,
    Repository,
    Task,
    TaskSpecification,
)

logger = logging.getLogger("taskmarshal.operations")


@contextmanager
def observed_operation(
    operation: str,
    *,
    work_id: str | None = None,
    attempt_id: str | None = None,
) -> Iterator[None]:
    started = time.monotonic()
    common = {"operation": operation, "work_id": work_id, "attempt_id": attempt_id}
    logger.info("operation.start", extra={**common, "reason_code": "operation.started"})
    try:
        yield
    except Exception as exc:
        logger.exception(
            "operation.failure",
            extra={
                **common,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "reason_code": getattr(exc, "code", "operation.unhandled_failure"),
            },
        )
        raise
    logger.info(
        "operation.success",
        extra={
            **common,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "reason_code": "operation.succeeded",
        },
    )


class ControlPlaneService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_project(self, command: ProjectCreate) -> Project:
        with observed_operation("project.create"):
            project = Project(**command.model_dump())
            self.session.add(project)
            self.session.commit()
            return project

    def list_projects(self) -> list[Project]:
        return list(self.session.scalars(select(Project).order_by(Project.created_at)))

    def create_repository(self, command: RepositoryCreate) -> Repository:
        self._require(Project, command.project_id, "project.not_found")
        values = command.model_dump(exclude={"access_validated"})
        if command.access_validated:
            values["validated_at"] = datetime.now(UTC)
        with observed_operation("repository.create"):
            repository = Repository(**values)
            self.session.add(repository)
            self.session.commit()
            return repository

    def list_repositories(self) -> list[Repository]:
        return list(self.session.scalars(select(Repository).order_by(Repository.created_at)))

    def create_agent(self, command: AgentCreate) -> Agent:
        with observed_operation("agent.create"):
            agent = Agent(**command.model_dump())
            self.session.add(agent)
            self.session.commit()
            return agent

    def list_agents(self) -> list[Agent]:
        return list(self.session.scalars(select(Agent).order_by(Agent.created_at)))

    def create_agent_configuration(
        self, agent_id: str, command: AgentConfigurationCreate
    ) -> AgentConfiguration:
        self._require(Agent, agent_id, "agent.not_found")
        latest = self.session.scalar(
            select(func.max(AgentConfiguration.version)).where(
                AgentConfiguration.agent_id == agent_id
            )
        )
        with observed_operation("agent_configuration.create"):
            configuration = AgentConfiguration(
                agent_id=agent_id,
                version=(latest or 0) + 1,
                **command.model_dump(),
            )
            self.session.add(configuration)
            self.session.commit()
            return configuration

    def list_agent_configurations(self) -> list[AgentConfiguration]:
        return list(
            self.session.scalars(
                select(AgentConfiguration).order_by(
                    AgentConfiguration.agent_id, AgentConfiguration.version
                )
            )
        )

    def create_task(self, command: TaskCreate) -> Task:
        self._require(Project, command.project_id, "project.not_found")
        with observed_operation("task.create"):
            task = Task(**command.model_dump())
            self.session.add(task)
            self.session.flush()
            self._event("task.created", task.id, reason_code="task.created")
            self.session.commit()
            return task

    def list_tasks(self) -> list[Task]:
        return list(self.session.scalars(select(Task).order_by(Task.created_at)))

    def get_task(self, work_id: str) -> Task:
        task = self.session.scalar(
            select(Task)
            .where(Task.id == work_id)
            .options(selectinload(Task.specifications), selectinload(Task.attempts))
        )
        if task is None:
            raise DomainError(404, "task.not_found", "Logical task was not found.")
        return task

    def create_task_specification(
        self, work_id: str, command: TaskSpecificationCreate
    ) -> TaskSpecification:
        task = self.get_task(work_id)
        self._require(Repository, command.repository_id, "repository.not_found")
        self._require(
            AgentConfiguration, command.actor_configuration_id, "actor_configuration.not_found"
        )
        self._require(
            AgentConfiguration,
            command.reviewer_configuration_id,
            "reviewer_configuration.not_found",
        )
        for dependency_id in command.dependency_ids:
            if dependency_id == work_id:
                raise DomainError(
                    422, "dependency.self_reference", "A task cannot depend on itself."
                )
            self._require(Task, dependency_id, "dependency.not_found")
        latest = self.session.scalar(
            select(func.max(TaskSpecification.version)).where(TaskSpecification.task_id == work_id)
        )
        payload = command.model_dump(mode="json")
        content_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with observed_operation("task_specification.create", work_id=work_id):
            specification = TaskSpecification(
                task_id=work_id,
                version=(latest or 0) + 1,
                content_hash=content_hash,
                **payload,
            )
            self.session.add(specification)
            self.session.flush()
            task.current_specification_id = specification.id
            if task.status in {TaskStatus.DRAFT, TaskStatus.READY}:
                task.status = TaskStatus.DRAFT
            self._event(
                "task.specification.created",
                work_id,
                reason_code="task_specification.version_created",
                payload={"specification_id": specification.id, "version": specification.version},
            )
            self.session.commit()
            return specification

    def readiness(self, work_id: str, *, persist_status: bool = True) -> dict[str, Any]:
        task = self.get_task(work_id)
        specification = (
            self.session.get(TaskSpecification, task.current_specification_id)
            if task.current_specification_id
            else None
        )
        repository = (
            self.session.get(Repository, specification.repository_id) if specification else None
        )
        actor = (
            self.session.get(AgentConfiguration, specification.actor_configuration_id)
            if specification
            else None
        )
        reviewer = (
            self.session.get(AgentConfiguration, specification.reviewer_configuration_id)
            if specification
            else None
        )
        dependency_statuses: list[str] = []
        if specification and specification.dependency_ids:
            dependencies = self.session.scalars(
                select(Task).where(Task.id.in_(specification.dependency_ids))
            )
            status_by_id = {dependency.id: dependency.status for dependency in dependencies}
            dependency_statuses = [
                status_by_id.get(dependency_id, "missing")
                for dependency_id in specification.dependency_ids
            ]
        report = evaluate_readiness(
            ReadinessContext(
                work_id=UUID(work_id),
                repository=self._as_dict(repository, ("url", "validated_at")),
                specification=self._as_dict(
                    specification,
                    (
                        "base_revision",
                        "goal",
                        "acceptance_criteria",
                        "verification_commands",
                        "limits",
                        "required_secret_refs",
                        "sandbox_policy",
                    ),
                ),
                actor_configuration=self._as_dict(actor, ("role_eligibility",)),
                reviewer_configuration=self._as_dict(reviewer, ("role_eligibility",)),
                available_secret_refs=frozenset(
                    repository.available_secret_refs if repository else []
                ),
                dependency_statuses=dependency_statuses,
            )
        )
        if persist_status and task.status in {TaskStatus.DRAFT, TaskStatus.READY}:
            desired = TaskStatus.READY if report.ready else TaskStatus.DRAFT
            if task.status != desired:
                task.status = desired
                self._event(
                    "task.readiness.changed",
                    work_id,
                    reason_code="readiness.satisfied" if report.ready else "readiness.unsatisfied",
                    payload={
                        "satisfied": report.satisfied_count,
                        "total": len(report.requirements),
                    },
                )
                self.session.commit()
        return {
            "work_id": work_id,
            "ready": report.ready,
            "satisfied": report.satisfied_count,
            "total": len(report.requirements),
            "requirements": [
                {
                    "code": requirement.code,
                    "satisfied": requirement.satisfied,
                    "remediation": requirement.remediation,
                }
                for requirement in report.requirements
            ],
        }

    def start_attempt(self, work_id: str) -> Attempt:
        task = self.get_task(work_id)
        report = self.readiness(work_id)
        failed = [item for item in report["requirements"] if not item["satisfied"]]
        if failed:
            raise DomainError(
                409,
                "task.not_ready",
                "Attempt start failed closed because readiness is incomplete.",
                failed,
            )
        specification = self.session.get(TaskSpecification, task.current_specification_id)
        if specification is None:
            raise DomainError(
                409, "task.specification_missing", "Task has no current specification."
            )
        configuration = self.session.get(AgentConfiguration, specification.actor_configuration_id)
        if configuration is None:
            raise DomainError(
                409, "actor_configuration.missing", "Actor configuration is unavailable."
            )
        active_attempts = self.session.scalar(
            select(func.count(Attempt.id)).where(
                Attempt.agent_configuration_id == configuration.id,
                Attempt.status.in_(("starting", "running")),
            )
        )
        if (active_attempts or 0) >= configuration.max_concurrency:
            raise DomainError(
                409,
                "agent.concurrency_exhausted",
                "The immutable agent configuration has no available concurrency slot.",
            )
        try:
            next_task_status, attempt_status = start_attempt(
                TaskStatus(task.status), report["ready"]
            )
        except InvalidTransition as exc:
            raise DomainError(409, "attempt.invalid_transition", str(exc)) from exc
        task.ownership_epoch += 1
        snapshot = self._as_dict(
            configuration,
            (
                "id",
                "version",
                "role_eligibility",
                "adapter_type",
                "provider",
                "model",
                "instructions",
                "max_concurrency",
                "timeout_seconds",
                "max_cost_usd",
            ),
        )
        with observed_operation("attempt.start", work_id=work_id):
            attempt = Attempt(
                work_id=work_id,
                task_specification_id=specification.id,
                agent_configuration_id=configuration.id,
                input_state_id=specification.content_hash,
                ownership_epoch=task.ownership_epoch,
                status=attempt_status,
                configuration_snapshot=snapshot,
            )
            task.status = next_task_status
            self.session.add(attempt)
            self.session.flush()
            self._event(
                "attempt.started",
                work_id,
                attempt.id,
                "attempt.manual_start",
                {"input_state_id": attempt.input_state_id},
            )
            self.session.commit()
            return attempt

    def _event(
        self,
        event_type: str,
        work_id: str | None,
        attempt_id: str | None = None,
        reason_code: str = "event.recorded",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            DomainEvent(
                event_type=event_type,
                work_id=work_id,
                attempt_id=attempt_id,
                reason_code=reason_code,
                payload=payload or {},
            )
        )

    def _require(self, model: type[Any], object_id: str, code: str) -> Any:
        value = self.session.get(model, object_id)
        if value is None:
            raise DomainError(404, code, f"Referenced {model.__name__} was not found.")
        return value

    @staticmethod
    def _as_dict(value: Any | None, fields: tuple[str, ...]) -> dict[str, Any] | None:
        if value is None:
            return None
        return {field: getattr(value, field) for field in fields}
