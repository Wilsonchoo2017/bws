"""Data coverage statistics API route."""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from api.dependencies import get_db

if TYPE_CHECKING:
    from db.pg.dual_writer import DualWriter

router = APIRouter(prefix="/stats", tags=["stats"])


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
