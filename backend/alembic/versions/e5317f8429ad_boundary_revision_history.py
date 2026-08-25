"""retain immutable boundary revision history

Revision ID: e5317f8429ad
Revises: d4158ef932bc
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5317f8429ad"
down_revision: str | None = "d4158ef932bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boundary_revisions",
        sa.Column("admin_unit_id", sa.Uuid(), nullable=False),
        sa.Column("parent_admin_unit_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("geometry", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["admin_unit_id"], ["admin_units.id"]),
        sa.ForeignKeyConstraint(["parent_admin_unit_id"], ["admin_units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "admin_unit_id", "version", name="uq_boundary_revision_unit_version"
        ),
        sa.UniqueConstraint(
            "admin_unit_id",
            "valid_from",
            name="uq_boundary_revision_unit_effective_date",
        ),
    )
    op.create_index(
        op.f("ix_boundary_revisions_admin_unit_id"),
        "boundary_revisions",
        ["admin_unit_id"],
    )
    op.create_index(op.f("ix_boundary_revisions_version"), "boundary_revisions", ["version"])
    op.create_index(
        op.f("ix_boundary_revisions_valid_from"), "boundary_revisions", ["valid_from"]
    )
    op.execute(
        """
        INSERT INTO boundary_revisions
          (admin_unit_id, parent_admin_unit_id, version, source, valid_from, valid_to,
           geometry, id, created_at, updated_at)
        SELECT id, parent_id, boundary_version, boundary_source, valid_from, valid_to,
               geometry, id, created_at, updated_at
        FROM admin_units WHERE geometry IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_boundary_revisions_valid_from"), table_name="boundary_revisions")
    op.drop_index(op.f("ix_boundary_revisions_version"), table_name="boundary_revisions")
    op.drop_index(op.f("ix_boundary_revisions_admin_unit_id"), table_name="boundary_revisions")
    op.drop_table("boundary_revisions")
