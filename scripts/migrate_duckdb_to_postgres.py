"""One-shot data migration from DuckDB to PostgreSQL.

Reads all tables from the DuckDB database and bulk-inserts into Postgres.
Handles JSON string -> Python dict conversion for JSONB columns.
Resets Postgres sequences after load.

Usage:
    python scripts/migrate_duckdb_to_postgres.py
"""

import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
from sqlalchemy import text

from config.settings import BWS_DB_PATH, POSTGRES_URL
from db.pg.engine import get_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migrate")

BATCH_SIZE = 1000

# Tables in dependency order (no FK deps, but logically ordered)
TABLE_ORDER = [
    "lego_items",
    "bricklink_items",
    "minifigures",
    "set_minifigures",
    "image_assets",
    "product_analysis",
    "bricklink_price_history",
    "bricklink_monthly_sales",
    "minifig_price_history",
    "brickeconomy_snapshots",
    "keepa_snapshots",
    "google_trends_snapshots",
    "google_trends_theme_snapshots",
    "mightyutan_products",
    "mightyutan_price_history",
    "toysrus_products",
    "toysrus_price_history",
    "shopee_products",
    "shopee_saturation",
    "shopee_scrape_history",
    "price_records",
    "portfolio_transactions",
    "portfolio_snapshots",
    "scrape_tasks",
    "scrape_task_attempts",
    "ml_feature_store",
    "ml_model_runs",
    "ml_prediction_snapshots",
]

# Columns that store JSON as VARCHAR/JSON in DuckDB -> JSONB in Postgres
JSONB_COLUMNS: dict[str, list[str]] = {
    "bricklink_price_history": [
        "six_month_new", "six_month_used", "current_new", "current_used",
    ],
    "minifig_price_history": [
        "six_month_new", "six_month_used", "current_new", "current_used",
    ],
    "product_analysis": [
        "dimensional_scores", "risks", "opportunities",
    ],
    "brickeconomy_snapshots": [
        "value_chart_json", "sales_trend_json", "candlestick_json",
    ],
    "keepa_snapshots": [
        "amazon_price_json", "new_price_json", "new_3p_fba_json",
        "new_3p_fbm_json", "used_price_json", "used_like_new_json",
        "buy_box_json", "list_price_json", "warehouse_deals_json",
        "collectible_json", "sales_rank_json",
    ],
    "google_trends_snapshots": ["interest_json"],
    "google_trends_theme_snapshots": ["interest_lego_json", "interest_bare_json"],
    "ml_feature_store": ["features_json"],
}


def _to_pg_json(value: object) -> object:
    """Wrap a Python dict/list in psycopg2 Json for JSONB insertion.

    DuckDB returns JSON columns as Python dicts/lists already.
    psycopg2 needs them wrapped in Json() to insert into JSONB columns.
    If the value is a string, parse it first.
    """
    from psycopg2.extras import Json

    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(value, (dict, list)):
        return Json(value)
    return None


def migrate_table(
    duck_conn: duckdb.DuckDBPyConnection,
    pg_engine: object,
    table_name: str,
) -> int:
    """Migrate one table from DuckDB to Postgres. Returns row count."""
    result = duck_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()  # noqa: S608
    total = result[0] if result else 0
    if total == 0:
        logger.info("  %s: empty, skipping", table_name)
        return 0

    # Get column names
    duck_conn.execute(f"SELECT * FROM {table_name} LIMIT 0")  # noqa: S608
    cols = [desc[0] for desc in duck_conn.description]

    json_cols = set(JSONB_COLUMNS.get(table_name, []))
    col_str = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    stmt = text(
        f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders}) "  # noqa: S608
        f"ON CONFLICT DO NOTHING"
    )

    migrated = 0
    with pg_engine.connect() as conn:
        offset = 0
        while offset < total:
            rows = duck_conn.execute(
                f"SELECT * FROM {table_name} LIMIT {BATCH_SIZE} OFFSET {offset}"  # noqa: S608
            ).fetchall()
            if not rows:
                break

            batch = []
            for row in rows:
                row_dict = dict(zip(cols, row))
                # Wrap any dict/list values for JSONB, and also handle
                # known JSON string columns
                for key, val in row_dict.items():
                    if isinstance(val, (dict, list)) or key in json_cols:
                        row_dict[key] = _to_pg_json(val)
                batch.append(row_dict)

            conn.execute(stmt, batch)
            conn.commit()
            migrated += len(batch)
            offset += BATCH_SIZE

            if migrated % 5000 == 0 or migrated == total:
                logger.info("  %s: %d / %d rows", table_name, migrated, total)

    return migrated


def reset_sequences(pg_engine: object) -> None:
    """Reset all Postgres SERIAL sequences to max(id) + 1."""
    with pg_engine.connect() as conn:
        for table in TABLE_ORDER:
            try:
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "  # noqa: S608
                    f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
                ))
            except Exception:
                logger.debug("Sequence reset skipped for %s", table)
        conn.commit()
    logger.info("Sequences reset to max(id) + 1")


def verify_counts(duck_conn: duckdb.DuckDBPyConnection, pg_engine: object) -> bool:
    """Verify row counts match between DuckDB and Postgres."""
    all_match = True
    with pg_engine.connect() as conn:
        for table in TABLE_ORDER:
            duck_count = duck_conn.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
            pg_count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            ).scalar()
            status = "OK" if duck_count == pg_count else "MISMATCH"
            if status == "MISMATCH":
                all_match = False
            logger.info(
                "  %s: DuckDB=%d  Postgres=%d  [%s]",
                table, duck_count, pg_count, status,
            )
    return all_match


def main() -> None:
    logger.info("DuckDB -> PostgreSQL migration")
    logger.info("Source: %s", BWS_DB_PATH)
    logger.info("Target: %s", POSTGRES_URL.rsplit("@", 1)[-1])

    if not BWS_DB_PATH.exists():
        logger.error("DuckDB file not found: %s", BWS_DB_PATH)
        sys.exit(1)

    duck_conn = duckdb.connect(str(BWS_DB_PATH), read_only=True)
    pg_engine = get_engine()

    start = time.time()
    total_rows = 0

    for table in TABLE_ORDER:
        try:
            count = migrate_table(duck_conn, pg_engine, table)
            total_rows += count
        except Exception:
            logger.exception("Failed to migrate %s", table)

    elapsed = time.time() - start
    logger.info("Migrated %d total rows in %.1fs", total_rows, elapsed)

    logger.info("Resetting sequences...")
    reset_sequences(pg_engine)

    logger.info("Verifying row counts...")
    all_match = verify_counts(duck_conn, pg_engine)

    duck_conn.close()

    if all_match:
        logger.info("Migration complete -- all counts match")
    else:
        logger.warning("Migration complete -- some counts have mismatches")
        sys.exit(1)


if __name__ == "__main__":
    main()
