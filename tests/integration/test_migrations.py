from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, Table, create_engine, inspect, text

from taskmarshal.persistence.tables import Base


def test_forward_and_rollback_migration_with_populated_database(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (id, name, description) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'test', '')"
            )
        )
    assert "attempts" in inspect(engine).get_table_names()

    command.downgrade(config, "base")
    assert "projects" not in inspect(engine).get_table_names()
    engine.dispose()


def test_revision_is_independent_of_current_orm_metadata(tmp_path: Path) -> None:
    database = tmp_path / "deterministic.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    future_table = Table(
        "future_model_table",
        Base.metadata,
        Column("id", Integer, primary_key=True),
    )
    engine = create_engine(f"sqlite:///{database}")
    try:
        command.upgrade(config, "head")
        assert "future_model_table" not in inspect(engine).get_table_names()

        future_table.create(engine)
        command.downgrade(config, "base")
        assert "future_model_table" in inspect(engine).get_table_names()
    finally:
        Base.metadata.remove(future_table)
        engine.dispose()
