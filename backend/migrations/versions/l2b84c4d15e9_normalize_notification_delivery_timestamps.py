"""normalize notification delivery timestamps to UTC

Revision ID: l2b84c4d15e9
Revises: k1a75b3c02d8
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "l2b84c4d15e9"
down_revision: Union[str, Sequence[str], None] = "k1a75b3c02d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Previous worker versions compared user schedules in Ho Chi Minh time and
    # also persisted delivery telemetry with that same naive local clock. The
    # API correctly serializes operational history as UTC, so normalize those
    # historical values before the UTC-writing worker starts.
    op.execute(
        """
        UPDATE notifications
        SET delivered_at = delivered_at - INTERVAL '7 hours'
        WHERE delivered_at IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE notification_deliveries
        SET next_attempt_at = next_attempt_at - INTERVAL '7 hours',
            last_attempt_at = CASE
                WHEN last_attempt_at IS NULL THEN NULL
                ELSE last_attempt_at - INTERVAL '7 hours'
            END,
            delivered_at = CASE
                WHEN delivered_at IS NULL THEN NULL
                ELSE delivered_at - INTERVAL '7 hours'
            END,
            updated_at = CASE
                WHEN last_attempt_at IS NULL THEN updated_at
                ELSE updated_at - INTERVAL '7 hours'
            END
        """
    )
    op.execute(
        """
        UPDATE notification_delivery_attempts
        SET created_at = created_at - INTERVAL '7 hours'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE notification_delivery_attempts
        SET created_at = created_at + INTERVAL '7 hours'
        """
    )
    op.execute(
        """
        UPDATE notification_deliveries
        SET next_attempt_at = next_attempt_at + INTERVAL '7 hours',
            last_attempt_at = CASE
                WHEN last_attempt_at IS NULL THEN NULL
                ELSE last_attempt_at + INTERVAL '7 hours'
            END,
            delivered_at = CASE
                WHEN delivered_at IS NULL THEN NULL
                ELSE delivered_at + INTERVAL '7 hours'
            END,
            updated_at = CASE
                WHEN last_attempt_at IS NULL THEN updated_at
                ELSE updated_at + INTERVAL '7 hours'
            END
        """
    )
    op.execute(
        """
        UPDATE notifications
        SET delivered_at = delivered_at + INTERVAL '7 hours'
        WHERE delivered_at IS NOT NULL
        """
    )
