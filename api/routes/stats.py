"""Data coverage statistics API route."""

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_db
from config.settings import _domain_registry

if TYPE_CHECKING:
    from db.pg.dual_writer import DualWriter

router = APIRouter(prefix="/stats", tags=["stats"])


# ---------------------------------------------------------------------------
# Source-to-domain mapping for cooldown lookups
# ---------------------------------------------------------------------------

_SOURCE_DOMAIN_MAP: dict[str, str] = {
    "bricklink": "bricklink.com",
    "brickeconomy": "brickeconomy.com",
    "keepa": "keepa.com",
    "google_trends": "__google_trends__",  # special: not a domain limiter
}


@router.get("/cooldowns")
async def get_cooldowns() -> dict:
    """Return cooldown status for all registered domain rate limiters."""
    sources: list[dict] = []

    for source_key, domain in _SOURCE_DOMAIN_MAP.items():
        if domain == "__google_trends__":
            # Google Trends uses its own cooldown mechanism
            try:
                from services.scrape_queue.executors import (
                    get_trends_cooldown_remaining,
                )

                remaining = get_trends_cooldown_remaining()
                sources.append({
                    "source": source_key,
                    "source_name": "Google Trends",
                    "is_blocked": remaining > 0,
                    "cooldown_remaining_s": round(remaining, 0),
                    "escalation_level": 0,
                    "consecutive_failures": 0,
                    "max_per_hour": None,
                    "requests_this_hour": None,
                })
            except ImportError:
                pass
            continue

        limiter = _domain_registry.get(domain)
        if limiter is None:
            continue

        remaining = limiter.cooldown_remaining()
        sources.append({
            "source": source_key,
            "source_name": limiter._source_name,
            "is_blocked": limiter.is_blocked(),
            "cooldown_remaining_s": round(remaining, 0),
            "escalation_level": limiter._escalation_level,
            "consecutive_failures": limiter._consecutive_failures,
            "max_per_hour": limiter._max_per_hour,
            "requests_this_hour": len([
                ts for ts in limiter._timestamps
                if ts > time.monotonic() - 3600.0
            ]),
        })

    return {"success": True, "data": sources}


@router.post("/cooldowns/{source}/reset")
async def reset_cooldown(source: str) -> dict:
    """Reset cooldown for a specific source."""
    if source not in _SOURCE_DOMAIN_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown source: {source}",
        )

    domain = _SOURCE_DOMAIN_MAP[source]

    if domain == "__google_trends__":
        try:
            from services.scrape_queue.executors.google_trends import (
                _trends_cooldown,
            )

            _trends_cooldown.clear()
            return {"success": True, "message": f"Cooldown reset for Google Trends"}
        except ImportError:
            raise HTTPException(status_code=500, detail="Google Trends module not available")

    limiter = _domain_registry.get(domain)
    if limiter is None:
        raise HTTPException(status_code=404, detail=f"No rate limiter for {source}")

    limiter._blocked_until = 0.0
    limiter._escalation_level = 0
    limiter._consecutive_failures = 0
    limiter._was_blocked = False

    # Persist the reset to disk
    from config.settings import save_cooldowns

    save_cooldowns()

    return {"success": True, "message": f"Cooldown reset for {limiter._source_name}"}


# Each source: (label, table, set_number column, optional date column)
_SOURCES = [
    ("bricklink", "bricklink_items", "item_id", "last_scraped_at"),
    ("brickeconomy", "brickeconomy_snapshots", "set_number", "scraped_at"),
    ("keepa", "keepa_snapshots", "set_number", "scraped_at"),
    ("shopee", "shopee_products", "source_url", "scraped_at"),
    ("mightyutan", "mightyutan_products", "sku", "last_scraped_at"),
    ("toysrus", "toysrus_products", "sku", "last_scraped_at"),
    ("google_trends", "google_trends_snapshots", "set_number", "scraped_at"),
    ("minifigures", "set_minifigures", "set_item_id", "scraped_at"),
    ("images", "image_assets", "item_id", "downloaded_at"),
    ("ml_predictions", "ml_prediction_snapshots", "set_number", "snapshot_date"),
]


@router.get("/coverage")
async def data_coverage(conn: "DualWriter" = Depends(get_db)) -> dict:
    """Return per-source data point counts and missing sets."""
    total_sets: int = conn.execute(
        "SELECT COUNT(*) FROM lego_items"
    ).fetchone()[0]

    all_set_numbers: set[str] = {
        row[0]
        for row in conn.execute("SELECT set_number FROM lego_items").fetchall()
    }

    sources: list[dict] = []
    for label, table, key_col, date_col in _SOURCES:
        row_count: int = conn.execute(
            f"SELECT COUNT(*) FROM {table}"  # noqa: S608
        ).fetchone()[0]

        distinct_sets: int = conn.execute(
            f"SELECT COUNT(DISTINCT {key_col}) FROM {table}"  # noqa: S608
        ).fetchone()[0]

        latest = None
        if date_col is not None:
            latest_row = conn.execute(
                f"SELECT MAX({date_col}) FROM {table}"  # noqa: S608
            ).fetchone()
            if latest_row and latest_row[0] is not None:
                latest = str(latest_row[0])

        covered_keys: set[str] = {
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT {key_col} FROM {table}"  # noqa: S608
            ).fetchall()
        }
        missing_count = len(all_set_numbers - covered_keys)

        sources.append({
            "source": label,
            "total_rows": row_count,
            "distinct_sets": distinct_sets,
            "missing_sets": missing_count,
            "coverage_pct": round(distinct_sets / total_sets * 100, 1) if total_sets > 0 else 0,
            "latest_scraped": latest,
        })

    return {
        "success": True,
        "data": {
            "total_sets": total_sets,
            "sources": sources,
        },
    }
