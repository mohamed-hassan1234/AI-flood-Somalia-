"""track notification provider dispatch and dead letters

Revision ID: f6428a9530be
Revises: e5317f8429ad
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6428a9530be"
down_revision: str | None = "e5317f8429ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.add_column(sa.Column("provider_message_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("last_error_code", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.drop_column("dead_lettered_at")
        batch.drop_column("last_attempted_at")
        batch.drop_column("last_error_code")
        batch.drop_column("provider_message_id")
