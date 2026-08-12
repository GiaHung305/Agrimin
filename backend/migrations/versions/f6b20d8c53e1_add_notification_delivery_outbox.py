"""add notification delivery outbox

Revision ID: f6b20d8c53e1
Revises: e5a19c7b42d0
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6b20d8c53e1"
down_revision: Union[str, Sequence[str], None] = "e5a19c7b42d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("device_token_id", sa.UUID(), nullable=False),
        sa.Column("delivery_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["device_token_id"], ["device_tokens.id"]),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_key"),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index("ix_notification_deliveries_notification_id", "notification_deliveries", ["notification_id"])
    op.create_index("ix_notification_deliveries_device_token_id", "notification_deliveries", ["device_token_id"])
    op.create_index("ix_notification_deliveries_next_attempt_at", "notification_deliveries", ["next_attempt_at"])
    op.create_index("ix_notification_delivery_due", "notification_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_notification_delivery_owner", "notification_deliveries", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("notification_deliveries")
