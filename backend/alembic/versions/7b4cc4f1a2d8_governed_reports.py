"""Add governed partner and internal reports."""

import sqlalchemy as sa

from alembic import op

revision = "7b4cc4f1a2d8"
down_revision = "260241f9242c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("admin_unit_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column(
            "classification",
            sa.Enum("INTERNAL", "PARTNER", "PUBLIC", name="classification"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "PUBLISHED", name="reportstatus"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reporting_period", sa.String(length=80), nullable=False),
        sa.Column("boundary_version", sa.String(length=80), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("source_lineage", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_admin_unit_id"), "reports", ["admin_unit_id"])
    op.create_index(op.f("ix_reports_alert_id"), "reports", ["alert_id"])
    op.create_index(op.f("ix_reports_classification"), "reports", ["classification"])
    op.create_index(op.f("ix_reports_status"), "reports", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_classification"), table_name="reports")
    op.drop_index(op.f("ix_reports_alert_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_admin_unit_id"), table_name="reports")
    op.drop_table("reports")
