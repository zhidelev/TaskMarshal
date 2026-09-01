from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


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
