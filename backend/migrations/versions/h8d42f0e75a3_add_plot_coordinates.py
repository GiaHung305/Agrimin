"""add plot coordinates

Revision ID: h8d42f0e75a3
Revises: g7c31e9d64f2
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h8d42f0e75a3"
down_revision: Union[str, Sequence[str], None] = "g7c31e9d64f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("farm_plots", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("farm_plots", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("farm_plots", sa.Column("elevation_m", sa.Float(), nullable=True))
    op.add_column(
        "farm_plots", sa.Column("location_accuracy_m", sa.Float(), nullable=True)
    )
    op.add_column(
        "farm_plots", sa.Column("location_source", sa.String(20), nullable=True)
    )
    op.add_column(
        "farm_plots", sa.Column("coordinates_updated_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("farm_plots", "coordinates_updated_at")
    op.drop_column("farm_plots", "location_source")
    op.drop_column("farm_plots", "location_accuracy_m")
    op.drop_column("farm_plots", "elevation_m")
    op.drop_column("farm_plots", "longitude")
    op.drop_column("farm_plots", "latitude")
