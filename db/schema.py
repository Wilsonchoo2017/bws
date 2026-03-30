"""DuckDB schema definitions for BWS.

Contains DDL for creating all required tables.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.schema")


# SQL statements for creating tables
BRICKLINK_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS bricklink_items (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL UNIQUE,
    item_type VARCHAR NOT NULL,
    title VARCHAR,
    weight VARCHAR,
    year_released INTEGER,
    image_url VARCHAR,
    parts_count INTEGER,
    theme VARCHAR,
    watch_status VARCHAR DEFAULT 'active',
    scrape_interval_days INTEGER DEFAULT 7,
    last_scraped_at TIMESTAMP,
    next_scrape_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

BRICKLINK_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS bricklink_price_history (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL,
    six_month_new JSON,
    six_month_used JSON,
    current_new JSON,
    current_used JSON,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

BRICKLINK_MONTHLY_SALES_DDL = """
CREATE TABLE IF NOT EXISTS bricklink_monthly_sales (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    condition VARCHAR NOT NULL,
    times_sold INTEGER,
    total_quantity INTEGER,
    min_price INTEGER,
    max_price INTEGER,
    avg_price INTEGER,
    currency VARCHAR DEFAULT 'USD',
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_id, year, month, condition)
);
"""

PRODUCT_ANALYSIS_DDL = """
CREATE TABLE IF NOT EXISTS product_analysis (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL UNIQUE,
    overall_score INTEGER,
    confidence INTEGER,
    action VARCHAR,
    urgency VARCHAR,
    dimensional_scores JSON,
    risks JSON,
    opportunities JSON,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

WORLDBRICKS_SETS_DDL = """
CREATE TABLE IF NOT EXISTS worldbricks_sets (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL UNIQUE,
    set_name VARCHAR,
    year_released INTEGER,
    year_retired INTEGER,
    parts_count INTEGER,
    dimensions VARCHAR,
    image_url VARCHAR,
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_PRODUCTS_DDL = """
CREATE TABLE IF NOT EXISTS shopee_products (
    id INTEGER PRIMARY KEY,
    title VARCHAR NOT NULL,
    price_display VARCHAR,
    price_cents INTEGER,
    sold_count VARCHAR,
    rating VARCHAR,
    shop_name VARCHAR,
    product_url VARCHAR UNIQUE,
    image_url VARCHAR,
    source_url VARCHAR,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_SCRAPE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS shopee_scrape_history (
    id INTEGER PRIMARY KEY,
    source_url VARCHAR NOT NULL,
    items_found INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    error VARCHAR,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

TOYSRUS_PRODUCTS_DDL = """
CREATE TABLE IF NOT EXISTS toysrus_products (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL,
    price_myr VARCHAR,
    brand VARCHAR,
    category VARCHAR,
    age_range VARCHAR,
    url VARCHAR,
    image_url VARCHAR,
    available BOOLEAN DEFAULT TRUE,
    last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

TOYSRUS_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS toysrus_price_history (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL,
    price_myr VARCHAR NOT NULL,
    available BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

LEGO_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS lego_items (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL UNIQUE,
    title VARCHAR,
    theme VARCHAR,
    year_released INTEGER,
    year_retired INTEGER,
    parts_count INTEGER,
    weight VARCHAR,
    image_url VARCHAR,
    rrp_cents INTEGER,
    rrp_currency VARCHAR DEFAULT 'MYR',
    retiring_soon BOOLEAN DEFAULT FALSE,
    last_enriched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

PRICE_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS price_records (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    price_cents INTEGER NOT NULL,
    currency VARCHAR NOT NULL DEFAULT 'MYR',
    title VARCHAR,
    url VARCHAR,
    shop_name VARCHAR,
    condition VARCHAR,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_SATURATION_DDL = """
CREATE TABLE IF NOT EXISTS shopee_saturation (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    listings_count INTEGER NOT NULL,
    unique_sellers INTEGER NOT NULL,
    min_price_cents INTEGER,
    max_price_cents INTEGER,
    avg_price_cents INTEGER,
    median_price_cents INTEGER,
    price_spread_pct FLOAT,
    saturation_score FLOAT NOT NULL,
    saturation_level VARCHAR NOT NULL,
    search_query VARCHAR NOT NULL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

BRICKRANKER_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS brickranker_items (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL UNIQUE,
    set_name VARCHAR,
    year_released INTEGER,
    retiring_soon BOOLEAN DEFAULT FALSE,
    expected_retirement_date VARCHAR,
    theme VARCHAR,
    image_url VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Sequence tables for auto-increment IDs
SEQUENCES_DDL = """
CREATE SEQUENCE IF NOT EXISTS bricklink_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_monthly_sales_id_seq;
CREATE SEQUENCE IF NOT EXISTS product_analysis_id_seq;
CREATE SEQUENCE IF NOT EXISTS worldbricks_sets_id_seq;
CREATE SEQUENCE IF NOT EXISTS brickranker_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_saturation_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_scrape_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS toysrus_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS toysrus_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS lego_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS price_records_id_seq;
"""

# Index creation statements
INDEXES_DDL = """
CREATE INDEX IF NOT EXISTS idx_bricklink_items_watch_status
    ON bricklink_items(watch_status);
CREATE INDEX IF NOT EXISTS idx_bricklink_items_next_scrape
    ON bricklink_items(next_scrape_at);
CREATE INDEX IF NOT EXISTS idx_bricklink_items_year
    ON bricklink_items(year_released);
CREATE INDEX IF NOT EXISTS idx_bricklink_price_history_item
    ON bricklink_price_history(item_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_bricklink_monthly_sales_item
    ON bricklink_monthly_sales(item_id, year, month);
CREATE INDEX IF NOT EXISTS idx_product_analysis_action
    ON product_analysis(action);
CREATE INDEX IF NOT EXISTS idx_product_analysis_score
    ON product_analysis(overall_score);
CREATE INDEX IF NOT EXISTS idx_worldbricks_set_number
    ON worldbricks_sets(set_number);
CREATE INDEX IF NOT EXISTS idx_brickranker_set_number
    ON brickranker_items(set_number);
CREATE INDEX IF NOT EXISTS idx_brickranker_retiring_soon
    ON brickranker_items(retiring_soon);
CREATE INDEX IF NOT EXISTS idx_shopee_products_url
    ON shopee_products(product_url);
CREATE INDEX IF NOT EXISTS idx_shopee_products_source
    ON shopee_products(source_url);
CREATE INDEX IF NOT EXISTS idx_shopee_products_scraped
    ON shopee_products(scraped_at);
CREATE INDEX IF NOT EXISTS idx_shopee_saturation_set
    ON shopee_saturation(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_toysrus_products_sku
    ON toysrus_products(sku);
CREATE INDEX IF NOT EXISTS idx_toysrus_products_available
    ON toysrus_products(available);
CREATE INDEX IF NOT EXISTS idx_toysrus_price_history_sku
    ON toysrus_price_history(sku, scraped_at);
CREATE INDEX IF NOT EXISTS idx_lego_items_set_number
    ON lego_items(set_number);
CREATE INDEX IF NOT EXISTS idx_price_records_set_source
    ON price_records(set_number, source, recorded_at);
CREATE INDEX IF NOT EXISTS idx_price_records_recorded
    ON price_records(recorded_at);
"""

ALL_DDL = [
    SEQUENCES_DDL,
    BRICKLINK_ITEMS_DDL,
    BRICKLINK_PRICE_HISTORY_DDL,
    BRICKLINK_MONTHLY_SALES_DDL,
    PRODUCT_ANALYSIS_DDL,
    WORLDBRICKS_SETS_DDL,
    BRICKRANKER_ITEMS_DDL,
    SHOPEE_PRODUCTS_DDL,
    SHOPEE_SATURATION_DDL,
    SHOPEE_SCRAPE_HISTORY_DDL,
    TOYSRUS_PRODUCTS_DDL,
    TOYSRUS_PRICE_HISTORY_DDL,
    LEGO_ITEMS_DDL,
    PRICE_RECORDS_DDL,
    INDEXES_DDL,
]


def _migrate_bricklink_items(conn: "DuckDBPyConnection") -> None:
    """Add parts_count and theme columns to bricklink_items."""
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'bricklink_items'"
        ).fetchall()
    }
    if "parts_count" not in existing:
        conn.execute("ALTER TABLE bricklink_items ADD COLUMN parts_count INTEGER")
    if "theme" not in existing:
        conn.execute("ALTER TABLE bricklink_items ADD COLUMN theme VARCHAR")


def _migrate_lego_items(conn: "DuckDBPyConnection") -> None:
    """Add columns introduced after initial table creation."""
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'lego_items'"
        ).fetchall()
    }
    if "rrp_cents" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN rrp_cents INTEGER")
    if "rrp_currency" not in existing:
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN rrp_currency VARCHAR DEFAULT 'MYR'"
        )
    if "retiring_soon" not in existing:
        # DuckDB cannot ALTER a table with dependent indexes
        conn.execute("DROP INDEX IF EXISTS idx_lego_items_set_number")
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN retiring_soon BOOLEAN DEFAULT FALSE"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lego_items_set_number "
            "ON lego_items(set_number)"
        )
    if "last_enriched_at" not in existing:
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN last_enriched_at TIMESTAMP"
        )


_SEQUENCE_TABLE_MAP = [
    ("bricklink_items_id_seq", "bricklink_items"),
    ("bricklink_price_history_id_seq", "bricklink_price_history"),
    ("bricklink_monthly_sales_id_seq", "bricklink_monthly_sales"),
    ("product_analysis_id_seq", "product_analysis"),
    ("worldbricks_sets_id_seq", "worldbricks_sets"),
    ("brickranker_items_id_seq", "brickranker_items"),
    ("shopee_products_id_seq", "shopee_products"),
    ("shopee_saturation_id_seq", "shopee_saturation"),
    ("shopee_scrape_history_id_seq", "shopee_scrape_history"),
    ("toysrus_products_id_seq", "toysrus_products"),
    ("toysrus_price_history_id_seq", "toysrus_price_history"),
    ("lego_items_id_seq", "lego_items"),
    ("price_records_id_seq", "price_records"),
]


def _sync_sequences(conn: "DuckDBPyConnection") -> None:
    """Sync all sequences to max(id) + 1 of their tables.

    Prevents primary key collisions when sequences fall behind
    existing data (e.g., after restores or manual inserts).

    DuckDB cannot DROP a sequence that a table DEFAULT depends on,
    so we first try DROP+CREATE. If that fails (dependency), we
    advance the sequence by calling nextval in a loop.
    """
    for seq_name, table_name in _SEQUENCE_TABLE_MAP:
        try:
            row = conn.execute(
                f"SELECT COALESCE(MAX(id), 0) FROM {table_name}"  # noqa: S608
            ).fetchone()
            max_id = row[0] if row else 0
            if max_id <= 0:
                continue

            target = max_id + 1
            try:
                conn.execute(f"DROP SEQUENCE IF EXISTS {seq_name}")
                conn.execute(
                    f"CREATE SEQUENCE {seq_name} START {target}"
                )
            except Exception:  # noqa: BLE001
                # Sequence has a table DEFAULT dependency -- advance it instead
                curr = 0
                while curr < target:
                    curr = conn.execute(
                        f"SELECT nextval('{seq_name}')"  # noqa: S608
                    ).fetchone()[0]
        except Exception:  # noqa: BLE001
            # Table may not exist yet on first init
            pass


def _rebuild_all_tables(conn: "DuckDBPyConnection") -> None:
    """Rebuild all non-empty tables to repair PK index corruption.

    DuckDB fatal crashes (e.g., ungraceful server stop mid-write) can
    corrupt the ART index backing PRIMARY KEYs, causing subsequent
    UPDATEs to fail with uncatchable FATAL 'duplicate key' errors.

    These errors call abort() and cannot be caught by Python try/except,
    so we must rebuild proactively when corruption is suspected.
    """
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
    ).fetchall()

    for (table_name,) in tables:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
            ).fetchone()
            if not count or count[0] == 0:
                continue
            _rebuild_table(conn, table_name)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to rebuild %s", table_name)


def _rebuild_table(conn: "DuckDBPyConnection", table_name: str) -> None:
    """Rebuild a table by copying data, dropping, and recreating.

    Preserves all data. Drops and recreates all indexes.
    Uses explicit column names to handle tables where migrations
    added columns in a different order than the DDL.
    """
    tmp = f"{table_name}_rebuild"
    conn.execute(
        f"CREATE TABLE {tmp} AS SELECT * FROM {table_name}"  # noqa: S608
    )

    # Get column names from the backup (source of truth for data)
    backup_cols = [
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{tmp}' ORDER BY ordinal_position"  # noqa: S608
        ).fetchall()
    ]

    # Drop all indexes on this table
    indexes = conn.execute(
        "SELECT index_name FROM duckdb_indexes() "
        f"WHERE table_name = '{table_name}'"  # noqa: S608
    ).fetchall()
    for (idx_name,) in indexes:
        conn.execute(f"DROP INDEX IF EXISTS {idx_name}")

    conn.execute(f"DROP TABLE {table_name}")

    # Find the DDL for this table and recreate it
    table_ddl_map = {
        "bricklink_items": BRICKLINK_ITEMS_DDL,
        "bricklink_price_history": BRICKLINK_PRICE_HISTORY_DDL,
        "bricklink_monthly_sales": BRICKLINK_MONTHLY_SALES_DDL,
        "product_analysis": PRODUCT_ANALYSIS_DDL,
        "worldbricks_sets": WORLDBRICKS_SETS_DDL,
        "brickranker_items": BRICKRANKER_ITEMS_DDL,
        "shopee_products": SHOPEE_PRODUCTS_DDL,
        "shopee_saturation": SHOPEE_SATURATION_DDL,
        "shopee_scrape_history": SHOPEE_SCRAPE_HISTORY_DDL,
        "toysrus_products": TOYSRUS_PRODUCTS_DDL,
        "toysrus_price_history": TOYSRUS_PRICE_HISTORY_DDL,
        "lego_items": LEGO_ITEMS_DDL,
        "price_records": PRICE_RECORDS_DDL,
    }

    ddl = table_ddl_map.get(table_name)
    if ddl:
        conn.execute(ddl)
    else:
        conn.execute(
            f"CREATE TABLE {table_name} AS "  # noqa: S608
            f"SELECT * FROM {tmp} WHERE 1=0"
        )

    # Run migrations to add any columns not in the DDL
    if table_name == "bricklink_items":
        _migrate_bricklink_items(conn)
    if table_name == "lego_items":
        _migrate_lego_items(conn)

    # Get new table columns to find the intersection
    new_cols = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table_name}'"  # noqa: S608
        ).fetchall()
    }

    # Only copy columns that exist in both source and target
    shared_cols = [c for c in backup_cols if c in new_cols]
    cols_str = ", ".join(shared_cols)

    conn.execute(
        f"INSERT INTO {table_name} ({cols_str}) "  # noqa: S608
        f"SELECT {cols_str} FROM {tmp}"
    )
    conn.execute(f"DROP TABLE {tmp}")

    # Recreate indexes via the INDEXES_DDL (idempotent)
    for stmt in INDEXES_DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt and table_name in stmt:
            conn.execute(stmt)


def init_schema(conn: "DuckDBPyConnection") -> None:
    """Initialize the database schema.

    Creates all tables and indexes if they don't exist.

    Args:
        conn: DuckDB connection
    """
    for ddl in ALL_DDL:
        conn.execute(ddl)
    _migrate_bricklink_items(conn)
    _migrate_lego_items(conn)
    _sync_sequences(conn)
    # Flush WAL to reduce corruption risk on ungraceful shutdown
    try:
        conn.execute("CHECKPOINT")
    except Exception:  # noqa: BLE001
        pass


def drop_all_tables(conn: "DuckDBPyConnection") -> None:
    """Drop all tables (for testing/reset).

    Args:
        conn: DuckDB connection
    """
    conn.execute("DROP TABLE IF EXISTS product_analysis;")
    conn.execute("DROP TABLE IF EXISTS bricklink_monthly_sales;")
    conn.execute("DROP TABLE IF EXISTS bricklink_price_history;")
    conn.execute("DROP TABLE IF EXISTS bricklink_items;")
    conn.execute("DROP TABLE IF EXISTS worldbricks_sets;")
    conn.execute("DROP TABLE IF EXISTS brickranker_items;")
    conn.execute("DROP SEQUENCE IF EXISTS bricklink_items_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS bricklink_price_history_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS bricklink_monthly_sales_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS product_analysis_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS worldbricks_sets_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS brickranker_items_id_seq;")


def get_table_stats(conn: "DuckDBPyConnection") -> dict[str, int]:
    """Get row counts for all tables.

    Args:
        conn: DuckDB connection

    Returns:
        Dict mapping table name to row count
    """
    tables = [
        "bricklink_items",
        "bricklink_price_history",
        "bricklink_monthly_sales",
        "product_analysis",
        "worldbricks_sets",
        "brickranker_items",
    ]
    stats = {}
    for table in tables:
        try:
            result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
            stats[table] = result[0] if result else 0
        except Exception:  # noqa: BLE001
            stats[table] = 0
    return stats
