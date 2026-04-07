"""add keepa_failed to lego_items

Revision ID: a1b2c3d4e5f6
Revises: d2dca6e50fd4
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd2dca6e50fd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded -- the column may already exist from the runtime migration in db/schema.py
    op.execute(
        "ALTER TABLE lego_items ADD COLUMN IF NOT EXISTS keepa_failed BOOLEAN DEFAULT FALSE"
    )


def downgrade() -> None:
    op.drop_column('lego_items', 'keepa_failed')
