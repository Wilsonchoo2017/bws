"""add unique constraint to bricklink_monthly_sales

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-04-09 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'h9i0j1k2l3m4'
down_revision: Union[str, Sequence[str], None] = 'g8h9i0j1k2l3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove duplicates keeping the row with the latest scraped_at
    op.execute("""
        DELETE FROM bricklink_monthly_sales
        WHERE id NOT IN (
            SELECT DISTINCT ON (item_id, year, month, condition) id
            FROM bricklink_monthly_sales
            ORDER BY item_id, year, month, condition, scraped_at DESC NULLS LAST, id DESC
        )
    """)

    op.create_unique_constraint(
        'uq_bricklink_monthly_sales_item_year_month_cond',
        'bricklink_monthly_sales',
        ['item_id', 'year', 'month', 'condition'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_bricklink_monthly_sales_item_year_month_cond',
        'bricklink_monthly_sales',
        type_='unique',
    )
