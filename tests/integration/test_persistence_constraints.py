from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from taskmarshal.persistence.tables import (
    Agent,
    AgentConfiguration,
    Attempt,
    Project,
    Repository,
    Task,
    TaskSpecification,
)


def test_attempt_cannot_reference_another_logical_task(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        project = Project(name="Project")
        agent = Agent(name="Agent")
        session.add_all([project, agent])
        session.flush()
        configuration = AgentConfiguration(
            agent_id=agent.id,
            version=1,
            role_eligibility=["actor"],
            adapter_type="manual",
            provider="manual",
            model="manual",
            instructions="Manual",
            created_by="test",
        )
        repository = Repository(
            project_id=project.id, name="Repo", url="https://example.test/repo.git"
        )
        task = Task(project_id=project.id, title="Task")
        other_task = Task(project_id=project.id, title="Other task")
        session.add_all([configuration, repository, task, other_task])
        session.flush()
        specification = TaskSpecification(
            task_id=task.id,
            version=1,
            repository_id=repository.id,
            base_revision="abc",
            goal="Goal",
            acceptance_criteria=["Done"],
            verification_commands=["pytest"],
            actor_configuration_id=configuration.id,
            reviewer_configuration_id=configuration.id,
            limits={"max_tokens": 1},
            sandbox_policy={"network": "none"},
            authored_by="test",
            content_hash="hash",
        )
        session.add(specification)
        session.flush()
        attempt = Attempt(
            work_id=other_task.id,
            task_specification_id=specification.id,
            agent_configuration_id=configuration.id,
            input_state_id="input",
            ownership_epoch=1,
            configuration_snapshot={},
        )
        session.add(attempt)
        with pytest.raises(IntegrityError):
            session.commit()
