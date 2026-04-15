"""add wanted_count to bricklink_items

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, Sequence[str], None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE bricklink_items "
        "ADD COLUMN IF NOT EXISTS wanted_count INTEGER"
    )


def downgrade() -> None:
    op.drop_column("bricklink_items", "wanted_count")
