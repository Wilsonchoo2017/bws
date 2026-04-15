"""Simplify shopee_captcha_events schema - remove verification state columns

Removes automatic verification workflow state management. Keeps only timestamp
and snapshot tracking for manual captcha handling.

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-04-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, Sequence[str], None] = "m4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop columns related to automatic verification workflow
    op.drop_column("shopee_captcha_events", "status")
    op.drop_column("shopee_captcha_events", "verified_at")
    op.drop_column("shopee_captcha_events", "resolved_at")
    op.drop_column("shopee_captcha_events", "resolution_duration_s")
    op.drop_column("shopee_captcha_events", "notes")


def downgrade() -> None:
    # Restore columns for rollback
    op.execute(
        "ALTER TABLE shopee_captcha_events "
        "ADD COLUMN status VARCHAR NOT NULL DEFAULT 'pending', "
        "ADD COLUMN verified_at TIMESTAMPTZ, "
        "ADD COLUMN resolved_at TIMESTAMPTZ, "
        "ADD COLUMN resolution_duration_s INTEGER, "
        "ADD COLUMN notes VARCHAR"
    )
