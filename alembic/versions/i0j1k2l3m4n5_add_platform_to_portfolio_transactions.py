"""Add platform to portfolio_transactions.

Nullable VARCHAR(100) column for tracking which platform/marketplace
was used for SELL transactions (e.g. Carousell, Facebook, BrickLink).

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-04-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'i0j1k2l3m4n5'
down_revision: Union[str, Sequence[str], None] = 'h9i0j1k2l3m4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'portfolio_transactions',
        sa.Column('platform', sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('portfolio_transactions', 'platform')
