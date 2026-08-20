"""remove duplicated crop from farm profiles

Revision ID: j0f64a2b91c7
Revises: i9e53a1f86b4
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j0f64a2b91c7"
down_revision: Union[str, Sequence[str], None] = "i9e53a1f86b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("farm_profiles", "crop")


def downgrade() -> None:
    op.add_column(
        "farm_profiles",
        sa.Column("crop", sa.String(length=100), nullable=True),
    )
