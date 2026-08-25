"""add governed indicator registry and observation linkage

Revision ID: c28f3e3c51a1
Revises: b61d91ac772e
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c28f3e3c51a1"
down_revision: str | None = "b61d91ac772e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "indicator_definitions",
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("value_kind", sa.String(length=40), nullable=False),
        sa.Column("minimum_value", sa.Float(), nullable=True),
        sa.Column("maximum_value", sa.Float(), nullable=True),
        sa.Column("aggregation_method", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("definition_source", sa.String(length=500), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
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
    )
    op.create_index(op.f("ix_indicator_definitions_code"), "indicator_definitions", ["code"], unique=True)
    op.create_index(op.f("ix_indicator_definitions_domain"), "indicator_definitions", ["domain"])
    with op.batch_alter_table("observations") as batch:
        batch.add_column(sa.Column("indicator_definition_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_observations_indicator_definition",
            "indicator_definitions",
            ["indicator_definition_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("observations") as batch:
        batch.drop_constraint("fk_observations_indicator_definition", type_="foreignkey")
        batch.drop_column("indicator_definition_id")
    op.drop_index(op.f("ix_indicator_definitions_domain"), table_name="indicator_definitions")
    op.drop_index(op.f("ix_indicator_definitions_code"), table_name="indicator_definitions")
    op.drop_table("indicator_definitions")
