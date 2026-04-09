"""create cart_banned table

Revision ID: g8h9i0j1k2l3
Revises: f7a8b9c0d1e2
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g8h9i0j1k2l3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS cart_banned (
            id SERIAL PRIMARY KEY,
            set_number VARCHAR(20) NOT NULL UNIQUE,
            banned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)


def downgrade() -> None:
    op.drop_table('cart_banned')
