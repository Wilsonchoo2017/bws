"""Add supplier to portfolio_transactions.

Nullable VARCHAR(100) column for tracking which supplier/store
sold the items, enabling post-mortem analytics on supplier quality.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'portfolio_transactions',
        sa.Column('supplier', sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('portfolio_transactions', 'supplier')
