"""persist governed boundary geometry

Revision ID: b61d91ac772e
Revises: 7b4cc4f1a2d8
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b61d91ac772e"
down_revision: str | None = "7b4cc4f1a2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_units", sa.Column("geometry", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("admin_units", "geometry")
