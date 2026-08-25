"""Require reproducible scenario geography and domain."""

import sqlalchemy as sa

from alembic import op

revision = "260241f9242c"
down_revision = "8a0a742073a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM scenarios")).scalar_one()
    if count:
        raise RuntimeError(
            "Existing scenarios require an approved geography/domain mapping before migration"
        )
    with op.batch_alter_table("scenarios") as batch:
        batch.add_column(sa.Column("admin_unit_id", sa.Uuid(), nullable=False))
        batch.add_column(
            sa.Column(
                "domain",
                sa.Enum(
                    "DROUGHT",
                    "RIVER_FLOOD",
                    "FLASH_FLOOD",
                    "FOOD_SECURITY",
                    name="riskdomain",
                ),
                nullable=False,
            )
        )
        batch.create_index(op.f("ix_scenarios_admin_unit_id"), ["admin_unit_id"], unique=False)
        batch.create_foreign_key(
            op.f("fk_scenarios_admin_unit_id_admin_units"),
            "admin_units",
            ["admin_unit_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("scenarios") as batch:
        batch.drop_constraint(op.f("fk_scenarios_admin_unit_id_admin_units"), type_="foreignkey")
        batch.drop_index(op.f("ix_scenarios_admin_unit_id"))
        batch.drop_column("domain")
        batch.drop_column("admin_unit_id")
