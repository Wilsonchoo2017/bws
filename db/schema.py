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
    is_sold_out BOOLEAN DEFAULT FALSE,
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

MIGHTYUTAN_PRODUCTS_DDL = """
CREATE TABLE IF NOT EXISTS mightyutan_products (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL,
    price_myr VARCHAR,
    original_price_myr VARCHAR,
    url VARCHAR,
    image_url VARCHAR,
    available BOOLEAN DEFAULT TRUE,
    quantity INTEGER DEFAULT 0,
    total_sold INTEGER DEFAULT 0,
    rating VARCHAR,
    rating_count INTEGER DEFAULT 0,
    last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

MIGHTYUTAN_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS mightyutan_price_history (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL,
    price_myr VARCHAR NOT NULL,
    available BOOLEAN DEFAULT TRUE,
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
    watchlist BOOLEAN DEFAULT FALSE,
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

PORTFOLIO_TRANSACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    txn_type VARCHAR NOT NULL,
    quantity INTEGER NOT NULL,
    price_cents INTEGER NOT NULL,
    currency VARCHAR NOT NULL DEFAULT 'MYR',
    condition VARCHAR NOT NULL DEFAULT 'new',
    txn_date TIMESTAMP NOT NULL,
    notes VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

PORTFOLIO_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    total_cost_cents BIGINT NOT NULL,
    total_market_value_cents BIGINT NOT NULL,
    unrealized_pl_cents BIGINT NOT NULL,
    realized_pl_cents BIGINT NOT NULL,
    holdings_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

MINIFIGURES_DDL = """
CREATE TABLE IF NOT EXISTS minifigures (
    id INTEGER PRIMARY KEY,
    minifig_id VARCHAR NOT NULL UNIQUE,
    name VARCHAR,
    image_url VARCHAR,
    year_released INTEGER,
    last_scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SET_MINIFIGURES_DDL = """
CREATE TABLE IF NOT EXISTS set_minifigures (
    id INTEGER PRIMARY KEY,
    set_item_id VARCHAR NOT NULL,
    minifig_id VARCHAR NOT NULL,
    quantity INTEGER DEFAULT 1,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(set_item_id, minifig_id)
);
"""

MINIFIG_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS minifig_price_history (
    id INTEGER PRIMARY KEY,
    minifig_id VARCHAR NOT NULL,
    six_month_new JSON,
    six_month_used JSON,
    current_new JSON,
    current_used JSON,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

IMAGE_ASSETS_DDL = """
CREATE TABLE IF NOT EXISTS image_assets (
    id INTEGER PRIMARY KEY,
    asset_type VARCHAR NOT NULL,
    item_id VARCHAR NOT NULL,
    source_url VARCHAR NOT NULL,
    local_path VARCHAR NOT NULL,
    file_size_bytes INTEGER,
    content_type VARCHAR DEFAULT 'image/png',
    downloaded_at TIMESTAMP,
    status VARCHAR DEFAULT 'pending',
    error VARCHAR,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_type, item_id)
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

SCRAPE_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS scrape_tasks (
    id INTEGER PRIMARY KEY,
    task_id VARCHAR NOT NULL UNIQUE,
    set_number VARCHAR NOT NULL,
    task_type VARCHAR NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3,
    status VARCHAR NOT NULL DEFAULT 'pending',
    depends_on VARCHAR,
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    error VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    locked_by VARCHAR,
    locked_at TIMESTAMP
);
"""

GOOGLE_TRENDS_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS google_trends_snapshots (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    keyword VARCHAR NOT NULL,
    search_property VARCHAR NOT NULL DEFAULT 'youtube',
    geo VARCHAR NOT NULL DEFAULT '',
    timeframe_start VARCHAR,
    timeframe_end VARCHAR,
    interest_json VARCHAR,
    peak_value INTEGER,
    peak_date VARCHAR,
    average_value FLOAT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

KEEPA_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS keepa_snapshots (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    asin VARCHAR,
    title VARCHAR,
    keepa_url VARCHAR,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_buy_box_cents INTEGER,
    current_amazon_cents INTEGER,
    current_new_cents INTEGER,
    lowest_ever_cents INTEGER,
    highest_ever_cents INTEGER,
    amazon_price_json VARCHAR,
    new_price_json VARCHAR,
    new_3p_fba_json VARCHAR,
    new_3p_fbm_json VARCHAR,
    used_price_json VARCHAR,
    used_like_new_json VARCHAR,
    buy_box_json VARCHAR,
    list_price_json VARCHAR,
    warehouse_deals_json VARCHAR,
    collectible_json VARCHAR,
    sales_rank_json VARCHAR,
    rating FLOAT,
    review_count INTEGER,
    tracking_users INTEGER,
    chart_screenshot_path VARCHAR
);
"""

# Sequence tables for auto-increment IDs
BRICKECONOMY_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS brickeconomy_snapshots (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    title VARCHAR,
    theme VARCHAR,
    subtheme VARCHAR,
    year_released INTEGER,
    pieces INTEGER,
    minifigs INTEGER,
    availability VARCHAR,
    image_url VARCHAR,
    brickeconomy_url VARCHAR,
    rrp_usd_cents INTEGER,
    rrp_gbp_cents INTEGER,
    rrp_eur_cents INTEGER,
    value_new_cents INTEGER,
    value_used_cents INTEGER,
    annual_growth_pct FLOAT,
    rating_value VARCHAR,
    review_count INTEGER,
    future_estimate_cents INTEGER,
    future_estimate_date VARCHAR,
    distribution_mean_cents INTEGER,
    distribution_stddev_cents INTEGER,
    value_chart_json JSON,
    sales_trend_json JSON,
    candlestick_json JSON
);
"""

SEQUENCES_DDL = """
CREATE SEQUENCE IF NOT EXISTS bricklink_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_monthly_sales_id_seq;
CREATE SEQUENCE IF NOT EXISTS product_analysis_id_seq;
CREATE SEQUENCE IF NOT EXISTS brickranker_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS minifigures_id_seq;
CREATE SEQUENCE IF NOT EXISTS set_minifigures_id_seq;
CREATE SEQUENCE IF NOT EXISTS minifig_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_saturation_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_scrape_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS mightyutan_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS mightyutan_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS toysrus_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS toysrus_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS lego_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS price_records_id_seq;
CREATE SEQUENCE IF NOT EXISTS portfolio_transactions_id_seq;
CREATE SEQUENCE IF NOT EXISTS portfolio_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS image_assets_id_seq;
CREATE SEQUENCE IF NOT EXISTS brickeconomy_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS keepa_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS google_trends_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS scrape_tasks_id_seq;
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
CREATE INDEX IF NOT EXISTS idx_brickranker_set_number
    ON brickranker_items(set_number);
CREATE INDEX IF NOT EXISTS idx_minifigures_minifig_id
    ON minifigures(minifig_id);
CREATE INDEX IF NOT EXISTS idx_set_minifigures_set
    ON set_minifigures(set_item_id);
CREATE INDEX IF NOT EXISTS idx_set_minifigures_minifig
    ON set_minifigures(minifig_id);
CREATE INDEX IF NOT EXISTS idx_minifig_price_history_item
    ON minifig_price_history(minifig_id, scraped_at);
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
CREATE INDEX IF NOT EXISTS idx_mightyutan_products_sku
    ON mightyutan_products(sku);
CREATE INDEX IF NOT EXISTS idx_mightyutan_products_available
    ON mightyutan_products(available);
CREATE INDEX IF NOT EXISTS idx_mightyutan_price_history_sku
    ON mightyutan_price_history(sku, scraped_at);
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
CREATE INDEX IF NOT EXISTS idx_portfolio_txn_set
    ON portfolio_transactions(set_number, txn_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_txn_date
    ON portfolio_transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date
    ON portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_image_assets_type_item
    ON image_assets(asset_type, item_id);
CREATE INDEX IF NOT EXISTS idx_image_assets_status
    ON image_assets(status);
CREATE INDEX IF NOT EXISTS idx_be_snapshots_set
    ON brickeconomy_snapshots(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_be_snapshots_scraped
    ON brickeconomy_snapshots(scraped_at);
CREATE INDEX IF NOT EXISTS idx_keepa_snapshots_set
    ON keepa_snapshots(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_keepa_snapshots_scraped
    ON keepa_snapshots(scraped_at);
CREATE INDEX IF NOT EXISTS idx_gtrends_snapshots_set
    ON google_trends_snapshots(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_gtrends_snapshots_scraped
    ON google_trends_snapshots(scraped_at);
CREATE INDEX IF NOT EXISTS idx_scrape_tasks_status_priority
    ON scrape_tasks(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_scrape_tasks_set_type
    ON scrape_tasks(set_number, task_type);
"""

ALL_DDL = [
    SEQUENCES_DDL,
    BRICKLINK_ITEMS_DDL,
    BRICKLINK_PRICE_HISTORY_DDL,
    BRICKLINK_MONTHLY_SALES_DDL,
    PRODUCT_ANALYSIS_DDL,
    IMAGE_ASSETS_DDL,
    BRICKRANKER_ITEMS_DDL,
    MINIFIGURES_DDL,
    SET_MINIFIGURES_DDL,
    MINIFIG_PRICE_HISTORY_DDL,
    SHOPEE_PRODUCTS_DDL,
    SHOPEE_SATURATION_DDL,
    SHOPEE_SCRAPE_HISTORY_DDL,
    MIGHTYUTAN_PRODUCTS_DDL,
    MIGHTYUTAN_PRICE_HISTORY_DDL,
    TOYSRUS_PRODUCTS_DDL,
    TOYSRUS_PRICE_HISTORY_DDL,
    LEGO_ITEMS_DDL,
    PRICE_RECORDS_DDL,
    PORTFOLIO_TRANSACTIONS_DDL,
    PORTFOLIO_SNAPSHOTS_DDL,
    BRICKECONOMY_SNAPSHOTS_DDL,
    KEEPA_SNAPSHOTS_DDL,
    GOOGLE_TRENDS_SNAPSHOTS_DDL,
    SCRAPE_TASKS_DDL,
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
    if "minifig_count" not in existing:
        conn.execute("ALTER TABLE bricklink_items ADD COLUMN minifig_count INTEGER")
    if "dimensions" not in existing:
        conn.execute("ALTER TABLE bricklink_items ADD COLUMN dimensions VARCHAR")
    if "has_instructions" not in existing:
        conn.execute("ALTER TABLE bricklink_items ADD COLUMN has_instructions BOOLEAN")


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
    if "minifig_count" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN minifig_count INTEGER")
    if "dimensions" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN dimensions VARCHAR")
    if "watchlist" not in existing:
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN watchlist BOOLEAN DEFAULT FALSE"
        )
    if "buy_rating" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN buy_rating INTEGER")


def _migrate_shopee_products(conn: "DuckDBPyConnection") -> None:
    """Add is_sold_out column to shopee_products."""
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'shopee_products'"
        ).fetchall()
    }
    if "is_sold_out" not in existing:
        conn.execute(
            "ALTER TABLE shopee_products ADD COLUMN is_sold_out BOOLEAN DEFAULT FALSE"
        )


_SEQUENCE_TABLE_MAP = [
    ("bricklink_items_id_seq", "bricklink_items"),
    ("bricklink_price_history_id_seq", "bricklink_price_history"),
    ("bricklink_monthly_sales_id_seq", "bricklink_monthly_sales"),
    ("product_analysis_id_seq", "product_analysis"),
    ("brickranker_items_id_seq", "brickranker_items"),
    ("minifigures_id_seq", "minifigures"),
    ("set_minifigures_id_seq", "set_minifigures"),
    ("minifig_price_history_id_seq", "minifig_price_history"),
    ("shopee_products_id_seq", "shopee_products"),
    ("shopee_saturation_id_seq", "shopee_saturation"),
    ("shopee_scrape_history_id_seq", "shopee_scrape_history"),
    ("mightyutan_products_id_seq", "mightyutan_products"),
    ("mightyutan_price_history_id_seq", "mightyutan_price_history"),
    ("toysrus_products_id_seq", "toysrus_products"),
    ("toysrus_price_history_id_seq", "toysrus_price_history"),
    ("lego_items_id_seq", "lego_items"),
    ("price_records_id_seq", "price_records"),
    ("portfolio_transactions_id_seq", "portfolio_transactions"),
    ("portfolio_snapshots_id_seq", "portfolio_snapshots"),
    ("image_assets_id_seq", "image_assets"),
    ("brickeconomy_snapshots_id_seq", "brickeconomy_snapshots"),
    ("keepa_snapshots_id_seq", "keepa_snapshots"),
    ("google_trends_snapshots_id_seq", "google_trends_snapshots"),
    ("scrape_tasks_id_seq", "scrape_tasks"),
]


def _sync_sequences(conn: "DuckDBPyConnection") -> None:
    """Sync all sequences to max(id) + 1 of their tables.

    Prevents primary key collisions when sequences fall behind
    existing data (e.g., after restores or manual inserts).

    Advances sequences by calling nextval rather than DROP+CREATE,
    which is safe for concurrent connections (nextval is atomic).
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
            curr = 0
            while curr < target:
                curr = conn.execute(
                    f"SELECT nextval('{seq_name}')"  # noqa: S608
                ).fetchone()[0]
        except Exception:  # noqa: BLE001
            # Table or sequence may not exist yet on first init
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
        "brickranker_items": BRICKRANKER_ITEMS_DDL,
        "minifigures": MINIFIGURES_DDL,
        "set_minifigures": SET_MINIFIGURES_DDL,
        "minifig_price_history": MINIFIG_PRICE_HISTORY_DDL,
        "shopee_products": SHOPEE_PRODUCTS_DDL,
        "shopee_saturation": SHOPEE_SATURATION_DDL,
        "shopee_scrape_history": SHOPEE_SCRAPE_HISTORY_DDL,
        "mightyutan_products": MIGHTYUTAN_PRODUCTS_DDL,
        "mightyutan_price_history": MIGHTYUTAN_PRICE_HISTORY_DDL,
        "toysrus_products": TOYSRUS_PRODUCTS_DDL,
        "toysrus_price_history": TOYSRUS_PRICE_HISTORY_DDL,
        "lego_items": LEGO_ITEMS_DDL,
        "price_records": PRICE_RECORDS_DDL,
        "portfolio_transactions": PORTFOLIO_TRANSACTIONS_DDL,
        "portfolio_snapshots": PORTFOLIO_SNAPSHOTS_DDL,
        "image_assets": IMAGE_ASSETS_DDL,
        "brickeconomy_snapshots": BRICKECONOMY_SNAPSHOTS_DDL,
        "keepa_snapshots": KEEPA_SNAPSHOTS_DDL,
        "google_trends_snapshots": GOOGLE_TRENDS_SNAPSHOTS_DDL,
        "scrape_tasks": SCRAPE_TASKS_DDL,
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
    if table_name == "shopee_products":
        _migrate_shopee_products(conn)

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
    _migrate_shopee_products(conn)
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
    conn.execute("DROP TABLE IF EXISTS brickranker_items;")
    conn.execute("DROP TABLE IF EXISTS minifig_price_history;")
    conn.execute("DROP TABLE IF EXISTS set_minifigures;")
    conn.execute("DROP TABLE IF EXISTS minifigures;")
    conn.execute("DROP SEQUENCE IF EXISTS minifigures_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS set_minifigures_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS minifig_price_history_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS bricklink_items_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS bricklink_price_history_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS bricklink_monthly_sales_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS product_analysis_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS brickranker_items_id_seq;")
    conn.execute("DROP TABLE IF EXISTS image_assets;")
    conn.execute("DROP SEQUENCE IF EXISTS image_assets_id_seq;")
    conn.execute("DROP TABLE IF EXISTS portfolio_transactions;")
    conn.execute("DROP TABLE IF EXISTS portfolio_snapshots;")
    conn.execute("DROP SEQUENCE IF EXISTS portfolio_transactions_id_seq;")
    conn.execute("DROP SEQUENCE IF EXISTS portfolio_snapshots_id_seq;")
    conn.execute("DROP TABLE IF EXISTS brickeconomy_snapshots;")
    conn.execute("DROP SEQUENCE IF EXISTS brickeconomy_snapshots_id_seq;")
    conn.execute("DROP TABLE IF EXISTS keepa_snapshots;")
    conn.execute("DROP SEQUENCE IF EXISTS keepa_snapshots_id_seq;")
    conn.execute("DROP TABLE IF EXISTS google_trends_snapshots;")
    conn.execute("DROP SEQUENCE IF EXISTS google_trends_snapshots_id_seq;")
    conn.execute("DROP TABLE IF EXISTS scrape_tasks;")
    conn.execute("DROP SEQUENCE IF EXISTS scrape_tasks_id_seq;")


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
        "brickranker_items",
        "minifigures",
        "set_minifigures",
        "minifig_price_history",
        "portfolio_transactions",
        "portfolio_snapshots",
        "image_assets",
        "brickeconomy_snapshots",
        "keepa_snapshots",
        "google_trends_snapshots",
        "scrape_tasks",
    ]
    stats = {}
    for table in tables:
        try:
            result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
            stats[table] = result[0] if result else 0
        except Exception:  # noqa: BLE001
            stats[table] = 0
    return stats
