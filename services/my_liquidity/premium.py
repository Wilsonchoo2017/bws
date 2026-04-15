"""MY-vs-BL price premium calculation.

Premium answers: "what fraction above BrickLink-USD do Malaysian
buyers pay on Shopee right now?". It's the single cheapest-to-compute
exit signal because both sides (MY median from shopee_competition,
BL USD from bricklink_monthly_sales or brickeconomy) already live in
the DB. Computed on demand \u2014 no persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from services.ml.currency import get_rate

BlSource = Literal[
    "bricklink_new",
    "bricklink_used",
    "brickeconomy_new",
    "brickeconomy_used",
    "brickeconomy_rrp_usd",
    "none",
]

_BL_STALE_MONTHS = 6


@dataclass(frozen=True)
class MyPremium:
    """Premium of Shopee MY listing prices over the BL USD benchmark."""

    set_number: str
    shopee_median_myr_cents: int | None
    shopee_p25_myr_cents: int | None
    shopee_p75_myr_cents: int | None
    shopee_listings_count: int
    bl_usd_cents: int | None
    bl_source: BlSource
    fx_rate_myr_per_usd: float | None
    premium_median_pct: float | None
    premium_p25_pct: float | None
    premium_p75_pct: float | None
    computed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["computed_at"] = self.computed_at.isoformat()
        return data


def compute_premium(conn: Any, set_number: str) -> MyPremium:
    """Compute the MY-vs-BL premium distribution for one set.

    Returns a fully-populated MyPremium even when data is missing \u2014
    None fields encode the gap. Callers should not filter None cases
    before surfacing; staleness tier is recorded in `bl_source`.
    """
    shopee = _fetch_shopee_distribution(conn, set_number)
    bl_cents, bl_source = _fetch_bl_usd_cents(conn, set_number)

    year = datetime.now(timezone.utc).year
    fx_rate = get_rate("MYR", year=year)

    premium_median_pct = _premium_pct(shopee["median"], bl_cents, fx_rate)
    premium_p25_pct = _premium_pct(shopee["p25"], bl_cents, fx_rate)
    premium_p75_pct = _premium_pct(shopee["p75"], bl_cents, fx_rate)

    return MyPremium(
        set_number=set_number,
        shopee_median_myr_cents=shopee["median"],
        shopee_p25_myr_cents=shopee["p25"],
        shopee_p75_myr_cents=shopee["p75"],
        shopee_listings_count=shopee["count"],
        bl_usd_cents=bl_cents,
        bl_source=bl_source,
        fx_rate_myr_per_usd=fx_rate,
        premium_median_pct=premium_median_pct,
        premium_p25_pct=premium_p25_pct,
        premium_p75_pct=premium_p75_pct,
        computed_at=datetime.now(timezone.utc),
    )


def _premium_pct(
    myr_cents: int | None,
    bl_usd_cents: int | None,
    fx_rate: float | None,
) -> float | None:
    """Return (myr / (bl_usd * fx) - 1) * 100, or None when any input is missing."""
    if myr_cents is None or bl_usd_cents is None or fx_rate is None:
        return None
    if bl_usd_cents <= 0 or fx_rate <= 0:
        return None
    expected_myr = bl_usd_cents * fx_rate
    if expected_myr <= 0:
        return None
    return (myr_cents / expected_myr - 1.0) * 100.0


def _fetch_shopee_distribution(conn: Any, set_number: str) -> dict[str, int | None]:
    """Pull MYR cent p25/median/p75 from the latest competition snapshot.

    Prefers per-listing percentile_cont when the latest snapshot has
    enough listings; falls back to the snapshot-level
    median/avg columns when not. Returns ints or None.
    """
    row = conn.execute(
        """
        SELECT id, listings_count, median_price_cents, avg_price_cents
        FROM shopee_competition_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()

    if row is None:
        return {"median": None, "p25": None, "p75": None, "count": 0}

    snapshot_id, listings_count, median_c, _avg_c = row
    pct_row = conn.execute(
        """
        SELECT
            percentile_cont(0.25) WITHIN GROUP (ORDER BY price_cents) AS p25,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY price_cents) AS p50,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY price_cents) AS p75,
            COUNT(price_cents) AS n
        FROM shopee_competition_listings
        WHERE snapshot_id = ?
          AND price_cents IS NOT NULL
          AND is_sold_out = FALSE
          AND is_delisted = FALSE
        """,
        [snapshot_id],
    ).fetchone()

    if pct_row is None or pct_row[3] == 0:
        return {
            "median": int(median_c) if median_c is not None else None,
            "p25": None,
            "p75": None,
            "count": listings_count or 0,
        }

    p25, p50, p75, _n = pct_row
    return {
        "median": int(p50) if p50 is not None else (int(median_c) if median_c is not None else None),
        "p25": int(p25) if p25 is not None else None,
        "p75": int(p75) if p75 is not None else None,
        "count": listings_count or 0,
    }


def _fetch_bl_usd_cents(
    conn: Any, set_number: str
) -> tuple[int | None, BlSource]:
    """Resolve a USD-cents benchmark for a set via a fallback chain.

    Order: BL monthly new (fresh) \u2192 BL monthly used (fresh) \u2192 BE value_new \u2192
    BE value_used \u2192 BE rrp_usd. Staleness cutoff for BL is 6 months.
    """
    bl_new = _bl_recent_avg_price(conn, set_number, condition="new")
    if bl_new is not None:
        return bl_new, "bricklink_new"

    bl_used = _bl_recent_avg_price(conn, set_number, condition="used")
    if bl_used is not None:
        return bl_used, "bricklink_used"

    be_row = conn.execute(
        """
        SELECT value_new_cents, value_used_cents, rrp_usd_cents
        FROM brickeconomy_snapshots
        WHERE set_number = ?
        ORDER BY scraped_at DESC
        LIMIT 1
        """,
        [set_number],
    ).fetchone()

    if be_row is None:
        return None, "none"

    value_new, value_used, rrp_usd = be_row
    if value_new:
        return int(value_new), "brickeconomy_new"
    if value_used:
        return int(value_used), "brickeconomy_used"
    if rrp_usd:
        return int(rrp_usd), "brickeconomy_rrp_usd"
    return None, "none"


def _bl_recent_avg_price(
    conn: Any, set_number: str, *, condition: str
) -> int | None:
    """Average BL avg_price over the last _BL_STALE_MONTHS months.

    Returns None if the most-recent row is older than _BL_STALE_MONTHS
    (treats the series as stale \u2014 caller falls through to BrickEconomy).
    """
    row = conn.execute(
        """
        SELECT year, month
        FROM bricklink_monthly_sales
        WHERE set_number = ? AND condition = ? AND avg_price IS NOT NULL
        ORDER BY year DESC, month DESC
        LIMIT 1
        """,
        [set_number, condition],
    ).fetchone()

    if row is None:
        return None

    latest_year, latest_month = row
    now = datetime.now(timezone.utc)
    months_stale = (now.year - latest_year) * 12 + (now.month - latest_month)
    if months_stale > _BL_STALE_MONTHS:
        return None

    avg_row = conn.execute(
        """
        SELECT AVG(avg_price)::INTEGER
        FROM (
            SELECT avg_price
            FROM bricklink_monthly_sales
            WHERE set_number = ? AND condition = ? AND avg_price IS NOT NULL
            ORDER BY year DESC, month DESC
            LIMIT ?
        ) AS recent
        """,
        [set_number, condition, _BL_STALE_MONTHS],
    ).fetchone()

    if avg_row is None or avg_row[0] is None:
        return None
    return int(avg_row[0])
