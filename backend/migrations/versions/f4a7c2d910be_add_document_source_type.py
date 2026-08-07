"""add document source type

Revision ID: f4a7c2d910be
Revises: e18a7bd2c901
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a7c2d910be"
down_revision: Union[str, Sequence[str], None] = "e18a7bd2c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "source_type",
            sa.String(length=50),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.create_index("ix_documents_source_type", "documents", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_documents_source_type", table_name="documents")
    op.drop_column("documents", "source_type")
