"""link recommendations to pending actions

Revision ID: g7c31e9d64f2
Revises: f6b20d8c53e1
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7c31e9d64f2"
down_revision: Union[str, Sequence[str], None] = "f6b20d8c53e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "farm_recommendations",
        sa.Column("pending_action_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "farm_recommendations",
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "farm_recommendations",
        sa.Column("task_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_farm_recommendation_pending_action",
        "farm_recommendations",
        "pending_actions",
        ["pending_action_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_farm_recommendation_pending_action",
        "farm_recommendations",
        ["pending_action_id"],
    )
    op.create_foreign_key(
        "fk_farm_recommendation_task",
        "farm_recommendations",
        "farm_tasks",
        ["task_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_farm_recommendation_task",
        "farm_recommendations",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_farm_recommendation_task",
        "farm_recommendations",
        type_="unique",
    )
    op.drop_constraint(
        "fk_farm_recommendation_task",
        "farm_recommendations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_farm_recommendation_pending_action",
        "farm_recommendations",
        type_="unique",
    )
    op.drop_constraint(
        "fk_farm_recommendation_pending_action",
        "farm_recommendations",
        type_="foreignkey",
    )
    op.drop_column("farm_recommendations", "resolved_at")
    op.drop_column("farm_recommendations", "task_id")
    op.drop_column("farm_recommendations", "pending_action_id")
