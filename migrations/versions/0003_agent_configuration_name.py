"""Add a version-owned Agent configuration name.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

LEGACY_NAME = "Legacy configuration"


def upgrade() -> None:
    # A server default makes the additive migration safe for populated databases without
    # rewriting immutable configuration rows or disabling their history guards.
    op.add_column(
        "agent_configurations",
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
            server_default=sa.text(f"'{LEGACY_NAME}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configurations", "name")
