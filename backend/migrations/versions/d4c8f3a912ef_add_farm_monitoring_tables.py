"""add farm monitoring tables

Revision ID: d4c8f3a912ef
Revises: f4a7c2d910be
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4c8f3a912ef"
down_revision: Union[str, Sequence[str], None] = "f4a7c2d910be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farm_monitoring_schedules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("farm_profile_id", sa.UUID(), nullable=False),
        sa.Column("crop", sa.String(100), nullable=False),
        sa.Column("province", sa.String(100), nullable=False),
        sa.Column("reminder_type", sa.String(50), nullable=False),
        sa.Column("frequency_hours", sa.Integer(), nullable=False),
        sa.Column("notification_scope", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("consent_granted_at", sa.DateTime(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["farm_profile_id"], ["farm_profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_farm_monitoring_schedules_user_id", "farm_monitoring_schedules", ["user_id"])
    op.create_index("ix_farm_monitoring_schedules_farm_profile_id", "farm_monitoring_schedules", ["farm_profile_id"])
    op.create_index("ix_farm_monitoring_due", "farm_monitoring_schedules", ["status", "next_run_at"])
    op.create_index("ix_farm_monitoring_owner", "farm_monitoring_schedules", ["user_id", "status"])

    op.create_table(
        "farm_weather_observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("run_key", sa.String(255), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["farm_monitoring_schedules.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key"),
    )
    op.create_index("ix_farm_weather_observations_user_id", "farm_weather_observations", ["user_id"])
    op.create_index("ix_farm_weather_observations_schedule_id", "farm_weather_observations", ["schedule_id"])
    op.create_index("ix_farm_weather_observations_expires_at", "farm_weather_observations", ["expires_at"])
    op.create_index("ix_farm_weather_observation_owner", "farm_weather_observations", ["user_id", "observed_at"])

    op.create_table(
        "farm_risk_predictions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("observation_id", sa.UUID(), nullable=False),
        sa.Column("risk_type", sa.String(80), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["observation_id"], ["farm_weather_observations.id"]),
        sa.ForeignKeyConstraint(["schedule_id"], ["farm_monitoring_schedules.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id"),
    )
    op.create_index("ix_farm_risk_predictions_user_id", "farm_risk_predictions", ["user_id"])
    op.create_index("ix_farm_risk_predictions_schedule_id", "farm_risk_predictions", ["schedule_id"])
    op.create_index("ix_farm_risk_predictions_risk_level", "farm_risk_predictions", ["risk_level"])
    op.create_index("ix_farm_risk_predictions_expires_at", "farm_risk_predictions", ["expires_at"])
    op.create_index("ix_farm_risk_prediction_owner", "farm_risk_predictions", ["user_id", "created_at"])

    op.create_table(
        "farm_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("schedule_id", sa.UUID(), nullable=False),
        sa.Column("prediction_id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["prediction_id"], ["farm_risk_predictions.id"]),
        sa.ForeignKeyConstraint(["schedule_id"], ["farm_monitoring_schedules.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
        sa.UniqueConstraint("notification_id"),
        sa.UniqueConstraint("prediction_id"),
    )
    op.create_index("ix_farm_recommendations_user_id", "farm_recommendations", ["user_id"])
    op.create_index("ix_farm_recommendations_schedule_id", "farm_recommendations", ["schedule_id"])
    op.create_index("ix_farm_recommendations_expires_at", "farm_recommendations", ["expires_at"])
    op.create_index("ix_farm_recommendation_owner", "farm_recommendations", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("farm_recommendations")
    op.drop_table("farm_risk_predictions")
    op.drop_table("farm_weather_observations")
    op.drop_table("farm_monitoring_schedules")
