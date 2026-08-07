"""version evaluation baselines

Revision ID: e18a7bd2c901
Revises: a7d2f9c1e4b0
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e18a7bd2c901"
down_revision: Union[str, Sequence[str], None] = "a7d2f9c1e4b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "golden_dataset",
        sa.Column("dataset_version", sa.String(length=50), server_default="v1", nullable=False),
    )
    op.create_index(
        "ix_golden_dataset_dataset_version",
        "golden_dataset",
        ["dataset_version"],
    )
    op.add_column(
        "eval_runs",
        sa.Column("dataset_version", sa.String(length=50), server_default="v1", nullable=False),
    )
    op.create_index("ix_eval_runs_dataset_version", "eval_runs", ["dataset_version"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_dataset_version", table_name="eval_runs")
    op.drop_column("eval_runs", "dataset_version")
    op.drop_index("ix_golden_dataset_dataset_version", table_name="golden_dataset")
    op.drop_column("golden_dataset", "dataset_version")
