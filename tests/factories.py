from __future__ import annotations

from uuid import uuid4

from sqlalchemy import MetaData, Table, insert, inspect
from sqlalchemy.orm import Session

from taskmarshal.persistence.tables import (
    Agent,
    AgentConfiguration,
    Artifact,
    Attempt,
    DomainEvent,
    Evidence,
    Project,
    Repository,
    Task,
    TaskSpecification,
)


def seed_chain(session: Session) -> dict[str, str]:
    """Populate every core table, including a current-version cycle and audit evidence."""
    project, agent = Project(name="Project"), Agent(name="Agent")
    session.add_all([project, agent])
    session.flush()
    has_configuration_name = "name" in {
        column["name"] for column in inspect(session.get_bind()).get_columns("agent_configurations")
    }
    if has_configuration_name:
        configurations = [
            AgentConfiguration(
                agent_id=agent.id,
                name=f"Configuration {version}",
                version=version,
                role_eligibility=["actor", "reviewer"],
                adapter_type="manual",
                provider="manual",
                model="manual",
                instructions=f"Instruction version {version}",
                created_by="test",
            )
            for version in (1, 2)
        ]
        session.add_all(configurations)
        session.flush()
        configuration_ids = [configuration.id for configuration in configurations]
    else:
        historical_table = Table(
            "agent_configurations", MetaData(), autoload_with=session.get_bind()
        )
        configuration_ids = [str(uuid4()), str(uuid4())]
        session.execute(
            insert(historical_table),
            [
                {
                    "id": configuration_id,
                    "agent_id": agent.id,
                    "version": version,
                    "role_eligibility": ["actor", "reviewer"],
                    "adapter_type": "manual",
                    "provider": "manual",
                    "model": "manual",
                    "instructions": f"Instruction version {version}",
                    "max_concurrency": 1,
                    "timeout_seconds": 1800,
                    "max_cost_usd": None,
                    "created_by": "test",
                }
                for configuration_id, version in zip(configuration_ids, (1, 2), strict=True)
            ],
        )
    repository = Repository(project_id=project.id, name="Repo", url="https://example.test/repo.git")
    task, other_task = (
        Task(project_id=project.id, title="Task", status="in_progress", ownership_epoch=1),
        Task(project_id=project.id, title="Other task"),
    )
    session.add_all([repository, task, other_task])
    session.flush()
    specification = TaskSpecification(
        task_id=task.id,
        version=1,
        repository_id=repository.id,
        base_revision="abc",
        goal="Goal",
        acceptance_criteria=["Done"],
        verification_commands=["pytest"],
        actor_configuration_id=configuration_ids[0],
        reviewer_configuration_id=configuration_ids[1],
        limits={"max_tokens": 1},
        sandbox_policy={"network": "none"},
        authored_by="test",
        content_hash="a" * 64,
    )
    session.add(specification)
    session.flush()
    task.current_specification_id = specification.id
    attempt = Attempt(
        work_id=task.id,
        task_specification_id=specification.id,
        agent_configuration_id=configuration_ids[0],
        input_state_id=specification.content_hash,
        ownership_epoch=1,
        status="running",
        configuration_snapshot={"id": configuration_ids[0], "version": 1, "model": "manual"},
    )
    session.add(attempt)
    session.flush()
    artifact = Artifact(attempt_id=attempt.id, kind="patch", uri="local://test", digest="digest")
    event = DomainEvent(
        event_type="attempt.started",
        work_id=task.id,
        attempt_id=attempt.id,
        reason_code="attempt.manual_start",
        payload={"input_state_id": specification.content_hash},
    )
    session.add_all([artifact, event])
    session.flush()
    evidence = Evidence(artifact_id=artifact.id, kind="test", passed=True)
    session.add(evidence)
    session.flush()
    session.commit()
    return {
        "project": project.id,
        "repository": repository.id,
        "agent": agent.id,
        "configuration": configuration_ids[0],
        "other_configuration": configuration_ids[1],
        "task": task.id,
        "other_task": other_task.id,
        "specification": specification.id,
        "attempt": attempt.id,
        "artifact": artifact.id,
        "evidence": evidence.id,
        "event": event.id,
    }
