"""align operational ownership and due-work indexes

Revision ID: i9e53a1f86b4
Revises: h8d42f0e75a3
Create Date: 2026-08-17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "i9e53a1f86b4"
down_revision: Union[str, Sequence[str], None] = "h8d42f0e75a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_farm_tasks_status_due",
        "farm_tasks",
        ["status", "due_at"],
    )
    op.create_index(
        "ix_farm_logs_owner_logged",
        "farm_logs",
        ["user_id", "logged_at"],
    )
    op.create_index(
        "ix_pending_actions_owner_status",
        "pending_actions",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_pending_actions_status_expiry",
        "pending_actions",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_device_tokens_owner_active",
        "device_tokens",
        ["user_id", "active"],
    )
    op.create_index(
        "ix_notifications_owner_created",
        "notifications",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_owner_created", table_name="notifications")
    op.drop_index("ix_device_tokens_owner_active", table_name="device_tokens")
    op.drop_index(
        "ix_pending_actions_status_expiry", table_name="pending_actions"
    )
    op.drop_index(
        "ix_pending_actions_owner_status", table_name="pending_actions"
    )
    op.drop_index("ix_farm_logs_owner_logged", table_name="farm_logs")
    op.drop_index("ix_farm_tasks_status_due", table_name="farm_tasks")
