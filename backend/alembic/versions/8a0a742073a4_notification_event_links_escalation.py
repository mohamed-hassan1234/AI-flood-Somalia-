"""notification_event_links_escalation"""

import sqlalchemy as sa

from alembic import op

revision = "8a0a742073a4"
down_revision = "1724017f8ab2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.add_column(sa.Column("alert_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("action_item_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("escalation_level", sa.Integer(), server_default="0", nullable=False)
        )
        batch.create_index(
            op.f("ix_notification_deliveries_action_item_id"),
            ["action_item_id"],
            unique=False,
        )
        batch.create_index(op.f("ix_notification_deliveries_alert_id"), ["alert_id"], unique=False)
        batch.create_foreign_key(
            op.f("fk_notification_deliveries_alert_id_alerts"),
            "alerts",
            ["alert_id"],
            ["id"],
        )
        batch.create_foreign_key(
            op.f("fk_notification_deliveries_action_item_id_action_items"),
            "action_items",
            ["action_item_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.drop_constraint(
            op.f("fk_notification_deliveries_action_item_id_action_items"),
            type_="foreignkey",
        )
        batch.drop_constraint(
            op.f("fk_notification_deliveries_alert_id_alerts"), type_="foreignkey"
        )
        batch.drop_index(op.f("ix_notification_deliveries_alert_id"))
        batch.drop_index(op.f("ix_notification_deliveries_action_item_id"))
        batch.drop_column("escalation_level")
        batch.drop_column("escalated_at")
        batch.drop_column("action_item_id")
        batch.drop_column("alert_id")
