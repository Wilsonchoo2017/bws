"""Sold-count velocity rollups over shopee_competition_snapshots.

Wraps `competition_repository.get_snapshot_velocity` into a typed
VelocityRollup with a per-day rate. The repository layer owns the
SQL; this layer owns the semantic interpretation (rate, dataclass,
serialization).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from services.shopee.competition_repository import get_snapshot_velocity


@dataclass(frozen=True)
class VelocityRollup:
    """Sold-count delta over a trailing window from competition snapshots."""

    set_number: str
    window_days: int
    total_sold_delta: int | None
    sold_per_day: float | None
    snapshots_in_window: int
    latest_snapshot_at: datetime | None
    prior_snapshot_at: datetime | None
    latest_total_sold: int | None
    prior_total_sold: int | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["latest_snapshot_at"] = (
            self.latest_snapshot_at.isoformat() if self.latest_snapshot_at else None
        )
        data["prior_snapshot_at"] = (
            self.prior_snapshot_at.isoformat() if self.prior_snapshot_at else None
        )
        return data


def compute_velocity(
    conn: Any,
    set_number: str,
    window_days: int = 30,
) -> VelocityRollup:
    """Return a trailing-window sold-count delta for a set.

    Interprets the raw snapshot diff as a per-day rate using the
    actual interval between the two snapshots (not `window_days`),
    so a 30-day window with only 21 days of data reports
    21-day_delta / 21 days.

    Notes on semantics:
    - `total_sold_count` at a snapshot sums the *current* per-listing
      sold counts; new listings that appeared since the prior snapshot
      inflate the delta, and delisted listings deflate it. This is
      acceptable for a rough demand signal but should not be treated
      as a ground-truth sales count.
    """
    raw = get_snapshot_velocity(conn, set_number, window_days)
    if raw is None:
        return VelocityRollup(
            set_number=set_number,
            window_days=window_days,
            total_sold_delta=None,
            sold_per_day=None,
            snapshots_in_window=0,
            latest_snapshot_at=None,
            prior_snapshot_at=None,
            latest_total_sold=None,
            prior_total_sold=None,
        )

    latest_at = raw["latest_at"]
    prior_at = raw["prior_at"]
    latest_total = raw["latest_total"]
    prior_total = raw["prior_total"]
    snapshots_in_window = raw["snapshots_in_window"]

    if prior_at is None or prior_total is None or latest_total is None:
        return VelocityRollup(
            set_number=set_number,
            window_days=window_days,
            total_sold_delta=None,
            sold_per_day=None,
            snapshots_in_window=snapshots_in_window,
            latest_snapshot_at=latest_at,
            prior_snapshot_at=prior_at,
            latest_total_sold=latest_total,
            prior_total_sold=prior_total,
        )

    delta = latest_total - prior_total
    interval_seconds = (latest_at - prior_at).total_seconds()
    interval_days = interval_seconds / 86400.0 if interval_seconds > 0 else None
    sold_per_day = (delta / interval_days) if interval_days and interval_days > 0 else None

    return VelocityRollup(
        set_number=set_number,
        window_days=window_days,
        total_sold_delta=delta,
        sold_per_day=sold_per_day,
        snapshots_in_window=snapshots_in_window,
        latest_snapshot_at=latest_at,
        prior_snapshot_at=prior_at,
        latest_total_sold=latest_total,
        prior_total_sold=prior_total,
    )
