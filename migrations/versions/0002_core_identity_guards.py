"""Enforce immutable input/event history and coherent attempt identities.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Frozen revision data: never import the current ORM or policy implementation here.
IMMUTABLE_TABLES = ("agent_configurations", "task_specifications", "domain_events")
ATTEMPT_IDENTITY = (
    "id",
    "work_id",
    "task_specification_id",
    "agent_configuration_id",
    "input_state_id",
    "ownership_epoch",
    "configuration_snapshot",
    "started_at",
)


def _preflight() -> None:
    if context.is_offline_mode():
        raise RuntimeError("migration.online_connection_required")
    connection = op.get_bind()
    if connection.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError("migration.unsupported_database")
    # SQLite batch recreation needs FK enforcement off on this migration-only connection.
    # Refuse an unsafe connection instead of silently changing a caller's transaction settings.
    if (
        connection.dialect.name == "sqlite"
        and connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    ):
        raise RuntimeError("migration.sqlite_foreign_keys_must_be_disabled")
    invalid_rows = (
        "SELECT 1 FROM tasks t LEFT JOIN task_specifications s "
        "ON t.current_specification_id = s.id AND t.id = s.task_id "
        "WHERE t.current_specification_id IS NOT NULL AND s.id IS NULL",
        "SELECT 1 FROM attempts a LEFT JOIN task_specifications s "
        "ON a.task_specification_id = s.id AND a.work_id = s.task_id "
        "AND a.agent_configuration_id = s.actor_configuration_id "
        "AND a.input_state_id = s.content_hash WHERE s.id IS NULL",
        "SELECT 1 FROM attempts GROUP BY work_id, ownership_epoch HAVING COUNT(*) > 1",
        "SELECT 1 FROM attempts WHERE ownership_epoch <= 0 OR id = work_id",
        "SELECT 1 FROM tasks WHERE ownership_epoch < 0",
        "SELECT 1 FROM agent_configurations WHERE version <= 0",
        "SELECT 1 FROM task_specifications WHERE version <= 0",
    )
    if any(connection.execute(sa.text(query)).first() is not None for query in invalid_rows):
        # No record values, credentials, or instruction content in migration errors.
        raise RuntimeError("migration.identity_conflict")
    if (
        connection.dialect.name == "sqlite"
        and connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None
    ):
        raise RuntimeError("migration.foreign_key_conflict")


def _create_immutability_guards() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table in IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                op.execute(
                    sa.text(
                        f"CREATE TRIGGER guard_{table}_{operation.lower()} BEFORE {operation} "
                        f"ON {table} BEGIN "
                        "SELECT RAISE(ABORT, 'persistence.immutable_history'); END"
                    )
                )
            conflict = "id = NEW.id"
            if table == "agent_configurations":
                conflict += " OR (agent_id = NEW.agent_id AND version = NEW.version)"
            elif table == "task_specifications":
                conflict += " OR (task_id = NEW.task_id AND version = NEW.version)"
            # SQLite REPLACE can skip DELETE triggers unless recursive_triggers is enabled.
            op.execute(
                sa.text(
                    f"CREATE TRIGGER guard_{table}_insert BEFORE INSERT ON {table} "
                    f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {conflict}) "
                    "BEGIN SELECT RAISE(ABORT, 'persistence.immutable_history'); END"
                )
            )
        op.execute(
            sa.text(
                "CREATE TRIGGER guard_attempt_insert BEFORE INSERT ON attempts "
                "WHEN EXISTS (SELECT 1 FROM attempts WHERE id = NEW.id OR "
                "(work_id = NEW.work_id AND ownership_epoch = NEW.ownership_epoch)) "
                "BEGIN SELECT RAISE(ABORT, 'persistence.immutable_attempt'); END"
            )
        )
        op.execute(
            sa.text(
                "CREATE TRIGGER guard_attempt_delete BEFORE DELETE ON attempts "
                "BEGIN SELECT RAISE(ABORT, 'persistence.immutable_attempt'); END"
            )
        )
        changed = " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in ATTEMPT_IDENTITY)
        op.execute(
            sa.text(
                "CREATE TRIGGER guard_attempt_identity BEFORE UPDATE ON attempts "
                f"WHEN {changed} BEGIN SELECT RAISE(ABORT, 'persistence.immutable_attempt'); END"
            )
        )
    else:
        op.execute(
            sa.text("""
            CREATE FUNCTION reject_immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'persistence.immutable_history' USING ERRCODE = '23514';
            END; $$
        """)
        )
        for table in IMMUTABLE_TABLES:
            op.execute(
                sa.text(
                    f"CREATE TRIGGER guard_{table} BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION reject_immutable_history()"
                )
            )
        changed = " OR ".join(
            f"OLD.{column} IS DISTINCT FROM NEW.{column}"
            if column != "configuration_snapshot"
            else (
                "OLD.configuration_snapshot::jsonb IS DISTINCT FROM "
                "NEW.configuration_snapshot::jsonb"
            )
            for column in ATTEMPT_IDENTITY
        )
        op.execute(
            sa.text(f"""
            CREATE FUNCTION reject_attempt_identity_change() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'persistence.immutable_attempt' USING ERRCODE = '23514';
                END IF;
                IF {changed} THEN
                    RAISE EXCEPTION 'persistence.immutable_attempt' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END; $$
        """)
        )
        op.execute(
            sa.text(
                "CREATE TRIGGER guard_attempt_identity BEFORE UPDATE OR DELETE ON attempts "
                "FOR EACH ROW EXECUTE FUNCTION reject_attempt_identity_change()"
            )
        )


def _drop_immutability_guards() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table in IMMUTABLE_TABLES:
            for operation in ("insert", "update", "delete"):
                op.execute(sa.text(f"DROP TRIGGER guard_{table}_{operation}"))
        op.execute(sa.text("DROP TRIGGER guard_attempt_identity"))
        op.execute(sa.text("DROP TRIGGER guard_attempt_insert"))
        op.execute(sa.text("DROP TRIGGER guard_attempt_delete"))
    else:
        for table in IMMUTABLE_TABLES:
            op.execute(sa.text(f"DROP TRIGGER guard_{table} ON {table}"))
        op.execute(sa.text("DROP TRIGGER guard_attempt_identity ON attempts"))
        op.execute(sa.text("DROP FUNCTION reject_immutable_history()"))
        op.execute(sa.text("DROP FUNCTION reject_attempt_identity_change()"))


def upgrade() -> None:
    _preflight()
    with op.batch_alter_table("agent_configurations") as batch:
        batch.create_check_constraint("ck_agent_configuration_version_positive", "version > 0")
    with op.batch_alter_table("task_specifications") as batch:
        batch.create_unique_constraint(
            "uq_task_specification_input_identity",
            ["id", "task_id", "actor_configuration_id", "content_hash"],
        )
        batch.create_check_constraint("ck_task_specification_version_positive", "version > 0")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_current_specification", type_="foreignkey")
        batch.create_foreign_key(
            "fk_tasks_current_specification_work",
            "task_specifications",
            ["current_specification_id", "id"],
            ["id", "task_id"],
        )
        batch.create_check_constraint("ck_task_epoch_nonnegative", "ownership_epoch >= 0")
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint("fk_attempt_specification_work", type_="foreignkey")
        batch.create_foreign_key(
            "fk_attempt_input_identity",
            "task_specifications",
            ["task_specification_id", "work_id", "agent_configuration_id", "input_state_id"],
            ["id", "task_id", "actor_configuration_id", "content_hash"],
        )
        batch.create_unique_constraint("uq_attempt_work_epoch", ["work_id", "ownership_epoch"])
        batch.create_check_constraint("ck_attempt_epoch_positive", "ownership_epoch > 0")
        batch.create_check_constraint("ck_attempt_distinct_identity", "id <> work_id")
    _create_immutability_guards()


def downgrade() -> None:
    _preflight()
    _drop_immutability_guards()
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint("fk_attempt_input_identity", type_="foreignkey")
        batch.drop_constraint("uq_attempt_work_epoch", type_="unique")
        batch.drop_constraint("ck_attempt_epoch_positive", type_="check")
        batch.drop_constraint("ck_attempt_distinct_identity", type_="check")
        batch.create_foreign_key(
            "fk_attempt_specification_work",
            "task_specifications",
            ["task_specification_id", "work_id"],
            ["id", "task_id"],
        )
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_current_specification_work", type_="foreignkey")
        batch.drop_constraint("ck_task_epoch_nonnegative", type_="check")
        batch.create_foreign_key(
            "fk_tasks_current_specification",
            "task_specifications",
            ["current_specification_id"],
            ["id"],
        )
    with op.batch_alter_table("task_specifications") as batch:
        batch.drop_constraint("uq_task_specification_input_identity", type_="unique")
        batch.drop_constraint("ck_task_specification_version_positive", type_="check")
    with op.batch_alter_table("agent_configurations") as batch:
        batch.drop_constraint("ck_agent_configuration_version_positive", type_="check")
