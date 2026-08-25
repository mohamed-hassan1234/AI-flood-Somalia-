"""add governed season definitions

Revision ID: d4158ef932bc
Revises: c28f3e3c51a1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4158ef932bc"
down_revision: str | None = "c28f3e3c51a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "season_definitions",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
    )
    op.create_index(op.f("ix_season_definitions_name"), "season_definitions", ["name"])
    op.create_index(op.f("ix_season_definitions_start"), "season_definitions", ["start"])
    op.create_index(op.f("ix_season_definitions_end"), "season_definitions", ["end"])


def downgrade() -> None:
    op.drop_index(op.f("ix_season_definitions_end"), table_name="season_definitions")
    op.drop_index(op.f("ix_season_definitions_start"), table_name="season_definitions")
    op.drop_index(op.f("ix_season_definitions_name"), table_name="season_definitions")
    op.drop_table("season_definitions")
