from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.factories import seed_chain

from taskmarshal.persistence.tables import (
    AgentConfiguration,
    Artifact,
    Attempt,
    DomainEvent,
    Evidence,
    Task,
    TaskSpecification,
)


@pytest.fixture
def identities(session_factory: sessionmaker[Session]) -> dict[str, str]:
    with session_factory() as session:
        return seed_chain(session)


def test_persisted_chain_has_distinct_stable_identifiers_and_immutable_inputs(
    session_factory: sessionmaker[Session], identities: dict[str, str]
) -> None:
    assert all(UUID(value) for value in identities.values())
    assert identities["task"] != identities["attempt"]
    with session_factory() as session:
        attempt = session.get(Attempt, identities["attempt"])
        specification = session.get(TaskSpecification, identities["specification"])
        assert attempt is not None and specification is not None
        assert attempt.work_id == specification.task_id == identities["task"]
        assert attempt.agent_configuration_id == specification.actor_configuration_id
        assert attempt.input_state_id == specification.content_hash
        assert attempt.ownership_epoch == 1
        assert attempt.configuration_snapshot["id"] == identities["configuration"]
        artifact = session.get(Artifact, identities["artifact"])
        evidence = session.get(Evidence, identities["evidence"])
        event = session.get(DomainEvent, identities["event"])
        assert artifact is not None and artifact.attempt_id == attempt.id
        assert evidence is not None and evidence.artifact_id == artifact.id
        assert (
            event is not None
            and event.attempt_id == attempt.id
            and event.work_id == attempt.work_id
        )


@pytest.mark.parametrize(
    "conflict",
    [
        "work",
        "configuration",
        "missing_configuration",
        "input",
        "epoch",
        "id",
        "work_as_id",
        "zero_epoch",
    ],
)
def test_attempt_identity_conflicts_fail_closed(
    session_factory: sessionmaker[Session], identities: dict[str, str], conflict: str
) -> None:
    values = dict(
        id=str(uuid4()),
        work_id=identities["task"],
        task_specification_id=identities["specification"],
        agent_configuration_id=identities["configuration"],
        input_state_id="a" * 64,
        ownership_epoch=2,
        status="starting",
        configuration_snapshot={},
    )
    changes = {
        "work": {"work_id": identities["other_task"]},
        "configuration": {"agent_configuration_id": identities["other_configuration"]},
        "missing_configuration": {"agent_configuration_id": str(uuid4())},
        "input": {"input_state_id": "b" * 64},
        "epoch": {"ownership_epoch": 1},
        "id": {"id": identities["attempt"]},
        "work_as_id": {"id": identities["task"]},
        "zero_epoch": {"ownership_epoch": 0},
    }
    values.update(changes[conflict])
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(insert(Attempt).values(**values))
            session.commit()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Attempt)) == 1


def test_current_specification_cannot_cross_tasks(
    session_factory: sessionmaker[Session], identities: dict[str, str]
) -> None:
    with session_factory() as session, pytest.raises(IntegrityError):
        session.execute(
            update(Task)
            .where(Task.id == identities["other_task"])
            .values(current_specification_id=identities["specification"])
        )
        session.commit()


@pytest.mark.parametrize(
    ("model", "identity", "changes"),
    [
        (AgentConfiguration, "configuration", {"name": "changed"}),
        (AgentConfiguration, "configuration", {"instructions": "changed"}),
        (TaskSpecification, "specification", {"goal": "changed"}),
        (DomainEvent, "event", {"id": "00000000-0000-0000-0000-000000000001"}),
        (DomainEvent, "event", {"payload": {"rewritten": True}}),
    ],
)
def test_history_rejects_updates_through_sql(
    session_factory: sessionmaker[Session],
    identities: dict[str, str],
    model: type,
    identity: str,
    changes: dict[str, object],
) -> None:
    with (
        session_factory() as session,
        pytest.raises(IntegrityError, match="persistence.immutable_history"),
    ):
        session.execute(update(model).where(model.id == identities[identity]).values(**changes))
        session.commit()


@pytest.mark.parametrize(
    ("model", "identity"),
    [
        (AgentConfiguration, "configuration"),
        (TaskSpecification, "specification"),
        (DomainEvent, "event"),
    ],
)
def test_history_rejects_deletes_through_sql(
    session_factory: sessionmaker[Session],
    identities: dict[str, str],
    model: type,
    identity: str,
) -> None:
    with (
        session_factory() as session,
        pytest.raises(IntegrityError, match="persistence.immutable_history"),
    ):
        session.execute(delete(model).where(model.id == identities[identity]))
        session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", str(uuid4())),
        ("work_id", str(uuid4())),
        ("task_specification_id", str(uuid4())),
        ("agent_configuration_id", str(uuid4())),
        ("input_state_id", "b" * 64),
        ("ownership_epoch", 2),
        ("configuration_snapshot", {"rewritten": True}),
        ("started_at", datetime(2000, 1, 1, tzinfo=UTC)),
    ],
)
def test_attempt_identity_and_snapshot_cannot_be_rewritten(
    session_factory: sessionmaker[Session], identities: dict[str, str], field: str, value: object
) -> None:
    with (
        session_factory() as session,
        pytest.raises(IntegrityError, match="persistence.immutable_attempt"),
    ):
        session.execute(
            update(Attempt).where(Attempt.id == identities["attempt"]).values(**{field: value})
        )
        session.commit()


def test_attempt_result_is_mutable_but_cannot_complete_logical_work(
    session_factory: sessionmaker[Session], identities: dict[str, str]
) -> None:
    with session_factory() as session:
        session.execute(
            update(Attempt)
            .where(Attempt.id == identities["attempt"])
            .values(
                status="candidate",
                actor_result={"claims_success": True},
                finished_at=datetime.now(UTC),
            )
        )
        session.commit()
    with session_factory() as session:
        task = session.get(Task, identities["task"])
        attempt = session.get(Attempt, identities["attempt"])
        assert task is not None and task.status == "in_progress"
        assert attempt is not None and attempt.status == "candidate"
        assert attempt.configuration_snapshot["version"] == 1


def test_attempt_cannot_be_deleted_and_reused_for_different_work(
    session_factory: sessionmaker[Session], identities: dict[str, str]
) -> None:
    with (
        session_factory() as session,
        pytest.raises(IntegrityError, match="persistence.immutable_attempt"),
    ):
        session.execute(delete(Attempt).where(Attempt.id == identities["attempt"]))
        session.commit()


@pytest.mark.parametrize(
    "table",
    [
        DomainEvent.__table__,
        AgentConfiguration.__table__,
        TaskSpecification.__table__,
        Attempt.__table__,
    ],
)
def test_upsert_cannot_replace_persisted_history(
    session_factory: sessionmaker[Session], identities: dict[str, str], table: object
) -> None:
    with session_factory() as session:
        values = dict(session.execute(select(table)).mappings().first())
        if session.get_bind().dialect.name == "sqlite":
            statement = insert(table).prefix_with("OR REPLACE").values(**values)
        else:
            field = "configuration_snapshot" if table is Attempt.__table__ else "id"
            changed = {"rewritten": True} if field == "configuration_snapshot" else str(uuid4())
            statement = (
                postgres_insert(table)
                .values(**values)
                .on_conflict_do_update(index_elements=["id"], set_={field: changed})
            )
        with pytest.raises(IntegrityError, match="persistence.immutable_"):
            session.execute(statement)
            session.commit()


@pytest.mark.parametrize("table", [AgentConfiguration.__table__, TaskSpecification.__table__])
@pytest.mark.parametrize("version", [0, 1])
def test_version_numbers_must_be_positive_and_unique(
    session_factory: sessionmaker[Session], identities: dict[str, str], table: object, version: int
) -> None:
    with session_factory() as session:
        original = dict(session.execute(select(table)).mappings().first())
        original.update(id=str(uuid4()), version=version)
        with pytest.raises(IntegrityError):
            session.execute(insert(table).values(**original))
            session.commit()
