"""Add set_number generated columns to BrickLink tables.

Adds a GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED column
to bricklink_items, bricklink_price_history, bricklink_monthly_sales,
and set_minifigures. This eliminates the recurring '-1' suffix mismatch
between BrickLink item_id ('75192-1') and lego_items.set_number ('75192').

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE bricklink_items "
        "ADD COLUMN set_number VARCHAR "
        "GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED"
    )
    op.execute(
        "ALTER TABLE bricklink_price_history "
        "ADD COLUMN set_number VARCHAR "
        "GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED"
    )
    op.execute(
        "ALTER TABLE bricklink_monthly_sales "
        "ADD COLUMN set_number VARCHAR "
        "GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED"
    )
    op.execute(
        "ALTER TABLE set_minifigures "
        "ADD COLUMN set_number VARCHAR "
        "GENERATED ALWAYS AS (SPLIT_PART(set_item_id, '-', 1)) STORED"
    )
    op.create_index(
        'idx_bricklink_items_set_number', 'bricklink_items', ['set_number']
    )
    op.create_index(
        'idx_bricklink_price_history_set_number',
        'bricklink_price_history',
        ['set_number'],
    )
    op.create_index(
        'idx_bricklink_monthly_sales_set_number',
        'bricklink_monthly_sales',
        ['set_number'],
    )
    op.create_index(
        'idx_set_minifigures_set_number', 'set_minifigures', ['set_number']
    )


def downgrade() -> None:
    op.drop_index('idx_set_minifigures_set_number')
    op.drop_index('idx_bricklink_monthly_sales_set_number')
    op.drop_index('idx_bricklink_price_history_set_number')
    op.drop_index('idx_bricklink_items_set_number')
    op.execute("ALTER TABLE set_minifigures DROP COLUMN set_number")
    op.execute("ALTER TABLE bricklink_monthly_sales DROP COLUMN set_number")
    op.execute("ALTER TABLE bricklink_price_history DROP COLUMN set_number")
    op.execute("ALTER TABLE bricklink_items DROP COLUMN set_number")
