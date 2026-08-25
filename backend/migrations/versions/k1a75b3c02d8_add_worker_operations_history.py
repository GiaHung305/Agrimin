"""add worker operations history

Revision ID: k1a75b3c02d8
Revises: j0f64a2b91c7
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k1a75b3c02d8"
down_revision: Union[str, Sequence[str], None] = "j0f64a2b91c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("delivery_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["delivery_id"], ["notification_deliveries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_delivery_attempts_delivery_id",
        "notification_delivery_attempts",
        ["delivery_id"],
    )
    op.create_index(
        "ix_notification_attempt_delivery_created",
        "notification_delivery_attempts",
        ["delivery_id", "created_at"],
    )
    op.create_index(
        "ix_notification_attempt_status_created",
        "notification_delivery_attempts",
        ["status", "created_at"],
    )

    op.create_table(
        "worker_failures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("worker_name", sa.String(50), nullable=False),
        sa.Column("cycle_name", sa.String(50), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_worker_failures_cycle_created",
        "worker_failures",
        ["cycle_name", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("worker_failures")
    op.drop_table("notification_delivery_attempts")
