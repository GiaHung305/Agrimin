"""add plots and crop seasons

Revision ID: e5a19c7b42d0
Revises: d4c8f3a912ef
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a19c7b42d0"
down_revision: Union[str, Sequence[str], None] = "d4c8f3a912ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "farm_plots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("farm_profile_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=True),
        sa.Column("location_note", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["farm_profile_id"], ["farm_profiles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_farm_plots_user_id", "farm_plots", ["user_id"])
    op.create_index("ix_farm_plots_farm_profile_id", "farm_plots", ["farm_profile_id"])
    op.create_index("ix_farm_plot_owner_status", "farm_plots", ["user_id", "status"])

    op.create_table(
        "crop_seasons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("plot_id", sa.UUID(), nullable=False),
        sa.Column("crop", sa.String(100), nullable=False),
        sa.Column("variety", sa.String(100), nullable=True),
        sa.Column("growth_stage", sa.String(100), nullable=True),
        sa.Column("planted_on", sa.Date(), nullable=True),
        sa.Column("expected_harvest_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plot_id"], ["farm_plots.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crop_seasons_user_id", "crop_seasons", ["user_id"])
    op.create_index("ix_crop_seasons_plot_id", "crop_seasons", ["plot_id"])
    op.create_index("ix_crop_season_owner_status", "crop_seasons", ["user_id", "status"])
    op.create_index(
        "uq_crop_season_active_plot",
        "crop_seasons",
        ["plot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.add_column("farm_monitoring_schedules", sa.Column("plot_id", sa.UUID(), nullable=True))
    op.add_column("farm_monitoring_schedules", sa.Column("crop_season_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_farm_monitoring_schedule_plot",
        "farm_monitoring_schedules",
        "farm_plots",
        ["plot_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_farm_monitoring_schedule_crop_season",
        "farm_monitoring_schedules",
        "crop_seasons",
        ["crop_season_id"],
        ["id"],
    )
    op.create_index("ix_farm_monitoring_schedules_plot_id", "farm_monitoring_schedules", ["plot_id"])
    op.create_index("ix_farm_monitoring_schedules_crop_season_id", "farm_monitoring_schedules", ["crop_season_id"])


def downgrade() -> None:
    op.drop_index("ix_farm_monitoring_schedules_crop_season_id", table_name="farm_monitoring_schedules")
    op.drop_index("ix_farm_monitoring_schedules_plot_id", table_name="farm_monitoring_schedules")
    op.drop_constraint(
        "fk_farm_monitoring_schedule_crop_season",
        "farm_monitoring_schedules",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_farm_monitoring_schedule_plot",
        "farm_monitoring_schedules",
        type_="foreignkey",
    )
    op.drop_column("farm_monitoring_schedules", "crop_season_id")
    op.drop_column("farm_monitoring_schedules", "plot_id")
    op.drop_table("crop_seasons")
    op.drop_table("farm_plots")
