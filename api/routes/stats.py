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
# (label, table, key_col, date_col, key_expr_override)
# key_expr_override: SQL expression to normalize key_col to match lego_items.set_number
# e.g. bricklink_items.item_id stores "75192-1" but lego_items.set_number is "75192"
_SOURCES = [
    ("bricklink", "bricklink_items", "item_id", "last_scraped_at", "REGEXP_REPLACE(item_id, '-\\d+$', '')"),
    ("brickeconomy", "brickeconomy_snapshots", "set_number", "scraped_at", None),
    ("keepa", "keepa_snapshots", "set_number", "scraped_at", None),
    ("google_trends", "google_trends_snapshots", "set_number", "scraped_at", None),
    ("minifigures", "set_minifigures", "set_item_id", "scraped_at", "REGEXP_REPLACE(set_item_id, '-\\d+$', '')"),
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
    for label, table, key_col, date_col, key_expr in _SOURCES:
        row_count: int = conn.execute(
            f"SELECT COUNT(*) FROM {table}"  # noqa: S608
        ).fetchone()[0]

        latest = None
        if date_col is not None:
            latest_row = conn.execute(
                f"SELECT MAX({date_col}) FROM {table}"  # noqa: S608
            ).fetchone()
            if latest_row and latest_row[0] is not None:
                latest = str(latest_row[0])

        # Use normalized key expression if the column doesn't match set_number directly
        select_expr = key_expr if key_expr else key_col
        covered_keys: set[str] = {
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT {select_expr} FROM {table}"  # noqa: S608
            ).fetchall()
        }
        # Only count sets that exist in lego_items
        covered_count = len(all_set_numbers & covered_keys)
        missing_count = len(all_set_numbers - covered_keys)

        sources.append({
            "source": label,
            "total_rows": row_count,
            "distinct_sets": covered_count,
            "missing_sets": missing_count,
            "coverage_pct": round(covered_count / total_sets * 100, 1) if total_sets > 0 else 0,
            "latest_scraped": latest,
        })

    return {
        "success": True,
        "data": {
            "total_sets": total_sets,
            "sources": sources,
        },
    }


# Sources used for per-set coverage (exclude google_trends — confirmed non-signal)
# (label, table, key_col, date_col, key_expr_override)
_SET_COVERAGE_SOURCES = [
    ("bricklink", "bricklink_items", "item_id", "last_scraped_at", "REGEXP_REPLACE(item_id, '-\\d+$', '')"),
    ("brickeconomy", "brickeconomy_snapshots", "set_number", "scraped_at", None),
    ("keepa", "keepa_snapshots", "set_number", "scraped_at", None),
    ("minifigures", "set_minifigures", "set_item_id", "scraped_at", "REGEXP_REPLACE(set_item_id, '-\\d+$', '')"),
]


@router.get("/coverage/sets")
async def set_coverage(
    conn: "DualWriter" = Depends(get_db),
    filter: str = "all",  # noqa: A002
    search: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Return per-set coverage breakdown across all sources.

    filter: 'all' | 'complete' | 'partial' | 'missing'
    search: filter by set_number or title substring
    """
    # Build per-set coverage with LEFT JOINs
    source_labels = [s[0] for s in _SET_COVERAGE_SOURCES]

    select_parts = ["li.set_number", "li.title"]
    join_parts: list[str] = []

    for label, table, key_col, date_col, key_expr in _SET_COVERAGE_SOURCES:
        alias = f"s_{label}"
        # Use normalized key expression for joining if keys have suffixes (e.g. "75192-1")
        norm_expr = key_expr if key_expr else key_col
        select_parts.append(
            f"CASE WHEN {alias}.norm_key IS NOT NULL THEN 1 ELSE 0 END AS has_{label}"
        )
        select_parts.append(
            f"{alias}.latest AS {label}_latest"
        )
        join_parts.append(
            f"LEFT JOIN ("
            f"SELECT {norm_expr} AS norm_key, MAX({date_col}) AS latest "
            f"FROM {table} GROUP BY {norm_expr}"
            f") {alias} ON {alias}.norm_key = li.set_number"
        )

    total_sources = len(_SET_COVERAGE_SOURCES)
    # Sum of has_* columns for filtering
    coverage_sum = " + ".join(
        f"CASE WHEN s_{label}.norm_key IS NOT NULL THEN 1 ELSE 0 END"
        for label, _, _, _, _ in _SET_COVERAGE_SOURCES
    )

    where_clauses: list[str] = []
    params: list = []
    if search:
        where_clauses.append(
            "(li.set_number ILIKE ? OR li.title ILIKE ?)"
        )
        like_val = f"%{search}%"
        params.extend([like_val, like_val])
    if filter == "complete":
        where_clauses.append(f"({coverage_sum}) = {total_sources}")
    elif filter == "partial":
        where_clauses.append(
            f"({coverage_sum}) > 0 AND ({coverage_sum}) < {total_sources}"
        )
    elif filter == "missing":
        where_clauses.append(f"({coverage_sum}) = 0")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    base_query = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM lego_items li "
        f"{' '.join(join_parts)} "
        f"{where_sql}"
    )

    # Count total matching rows
    count_row = conn.execute(
        f"SELECT COUNT(*) FROM ({base_query}) sub",  # noqa: S608
        params or None,
    ).fetchone()
    total_count = count_row[0] if count_row else 0

    # Paginated results ordered by coverage ascending (worst first)
    offset = (page - 1) * page_size
    paginated_query = (
        f"{base_query} "
        f"ORDER BY ({coverage_sum}) ASC, li.set_number ASC "
        f"LIMIT {page_size} OFFSET {offset}"
    )

    rows = conn.execute(paginated_query, params or None).fetchall()  # noqa: S608

    sets: list[dict] = []
    for row in rows:
        set_number = row[0]
        title = row[1]
        sources_dict: dict[str, dict] = {}
        for i, label in enumerate(source_labels):
            has_col = row[2 + i * 2]
            latest_col = row[3 + i * 2]
            sources_dict[label] = {
                "covered": bool(has_col),
                "latest": str(latest_col) if latest_col else None,
            }
        covered_count = sum(
            1 for s in sources_dict.values() if s["covered"]
        )
        sets.append({
            "set_number": set_number,
            "title": title,
            "sources": sources_dict,
            "covered_count": covered_count,
            "total_sources": total_sources,
        })

    # Summary distribution
    dist_query = (
        f"SELECT ({coverage_sum}) AS cov, COUNT(*) "
        f"FROM lego_items li {' '.join(join_parts)} "
        f"GROUP BY cov ORDER BY cov"
    )
    dist_rows = conn.execute(dist_query).fetchall()
    distribution = {int(r[0]): int(r[1]) for r in dist_rows}

    return {
        "success": True,
        "data": {
            "sets": sets,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "source_labels": source_labels,
            "total_sources": total_sources,
            "distribution": distribution,
        },
    }
