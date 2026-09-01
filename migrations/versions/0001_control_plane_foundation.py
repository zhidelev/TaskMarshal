"""Control-plane foundation schema.

Revision ID: 0001
Revises: None
"""
from __future__ import annotations

from alembic import op

from taskmarshal.persistence.tables import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), checkfirst=False)
