from __future__ import annotations

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
    configurations = [
        AgentConfiguration(
            agent_id=agent.id,
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
    repository = Repository(project_id=project.id, name="Repo", url="https://example.test/repo.git")
    task, other_task = (
        Task(project_id=project.id, title="Task", status="in_progress", ownership_epoch=1),
        Task(project_id=project.id, title="Other task"),
    )
    session.add_all([*configurations, repository, task, other_task])
    session.flush()
    specification = TaskSpecification(
        task_id=task.id,
        version=1,
        repository_id=repository.id,
        base_revision="abc",
        goal="Goal",
        acceptance_criteria=["Done"],
        verification_commands=["pytest"],
        actor_configuration_id=configurations[0].id,
        reviewer_configuration_id=configurations[1].id,
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
        agent_configuration_id=configurations[0].id,
        input_state_id=specification.content_hash,
        ownership_epoch=1,
        status="running",
        configuration_snapshot={"id": configurations[0].id, "version": 1, "model": "manual"},
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
        "configuration": configurations[0].id,
        "other_configuration": configurations[1].id,
        "task": task.id,
        "other_task": other_task.id,
        "specification": specification.id,
        "attempt": attempt.id,
        "artifact": artifact.id,
        "evidence": evidence.id,
        "event": event.id,
    }
