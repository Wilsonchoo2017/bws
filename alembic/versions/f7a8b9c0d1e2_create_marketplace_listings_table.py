"""create marketplace_listings table

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_listings (
            id SERIAL PRIMARY KEY,
            set_number VARCHAR(20) NOT NULL,
            platform VARCHAR(20) NOT NULL CHECK (platform IN ('shopee', 'carousell')),
            listing_price_cents INTEGER NOT NULL,
            listing_currency VARCHAR(5) NOT NULL DEFAULT 'MYR',
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'sold', 'delisted')),
            listed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (set_number, platform)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_marketplace_listings_set_number
        ON marketplace_listings (set_number)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_marketplace_listings_status
        ON marketplace_listings (status) WHERE status = 'active'
    """)


def downgrade() -> None:
    op.drop_table('marketplace_listings')
