"""add buy_category and derived probabilities to ml_prediction_snapshots

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-04-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, Sequence[str], None] = "l3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ml_prediction_snapshots "
        "ADD COLUMN IF NOT EXISTS buy_category VARCHAR(10), "
        "ADD COLUMN IF NOT EXISTS great_buy_probability DOUBLE PRECISION, "
        "ADD COLUMN IF NOT EXISTS good_buy_probability DOUBLE PRECISION"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ml_snapshot_buy_category "
        "ON ml_prediction_snapshots (snapshot_date, buy_category)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ml_snapshot_buy_category")
    op.drop_column("ml_prediction_snapshots", "good_buy_probability")
    op.drop_column("ml_prediction_snapshots", "great_buy_probability")
    op.drop_column("ml_prediction_snapshots", "buy_category")
