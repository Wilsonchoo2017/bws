"""create cart_removals table for auto-add cooldown tracking

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-04-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, Sequence[str], None] = 'i0j1k2l3m4n5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS cart_removals (
            id SERIAL PRIMARY KEY,
            set_number VARCHAR(20) NOT NULL UNIQUE,
            removed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cart_removals_removed_at
        ON cart_removals (removed_at)
    """)


def downgrade() -> None:
    op.drop_table('cart_removals')
