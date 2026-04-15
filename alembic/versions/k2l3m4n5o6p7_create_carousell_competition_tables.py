"""create carousell competition tables

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-04-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'k2l3m4n5o6p7'
down_revision: Union[str, Sequence[str], None] = 'j1k2l3m4n5o6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS carousell_competition_snapshots_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS carousell_competition_listings_id_seq")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carousell_competition_snapshots (
            id INTEGER PRIMARY KEY DEFAULT nextval('carousell_competition_snapshots_id_seq'),
            set_number VARCHAR NOT NULL,
            listings_count INTEGER NOT NULL,
            unique_sellers INTEGER NOT NULL,
            flipped_to_sold_count INTEGER,
            min_price_cents INTEGER,
            max_price_cents INTEGER,
            avg_price_cents INTEGER,
            median_price_cents INTEGER,
            saturation_score FLOAT NOT NULL,
            saturation_level VARCHAR NOT NULL,
            scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS carousell_competition_listings (
            id INTEGER PRIMARY KEY DEFAULT nextval('carousell_competition_listings_id_seq'),
            snapshot_id INTEGER NOT NULL,
            set_number VARCHAR NOT NULL,
            listing_id VARCHAR NOT NULL,
            listing_url VARCHAR NOT NULL,
            shop_id VARCHAR,
            seller_name VARCHAR,
            title VARCHAR NOT NULL,
            price_cents INTEGER,
            price_display VARCHAR,
            condition VARCHAR,
            image_url VARCHAR,
            time_ago VARCHAR,
            is_sold BOOLEAN DEFAULT FALSE,
            is_reserved BOOLEAN DEFAULT FALSE,
            is_delisted BOOLEAN DEFAULT FALSE,
            scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_carousell_comp_snapshots_set
            ON carousell_competition_snapshots(set_number, scraped_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_carousell_comp_listings_snapshot
            ON carousell_competition_listings(snapshot_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_carousell_comp_listings_set_listing
            ON carousell_competition_listings(set_number, listing_id, scraped_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS carousell_competition_listings")
    op.execute("DROP TABLE IF EXISTS carousell_competition_snapshots")
    op.execute("DROP SEQUENCE IF EXISTS carousell_competition_listings_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS carousell_competition_snapshots_id_seq")
