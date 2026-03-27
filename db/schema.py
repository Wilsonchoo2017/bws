"""DuckDB schema definitions for BWS.

Contains DDL for creating all required tables.
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


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
    SHOPEE_SCRAPE_HISTORY_DDL,
    TOYSRUS_PRODUCTS_DDL,
    TOYSRUS_PRICE_HISTORY_DDL,
    LEGO_ITEMS_DDL,
    PRICE_RECORDS_DDL,
    INDEXES_DDL,
]


def init_schema(conn: "DuckDBPyConnection") -> None:
    """Initialize the database schema.

    Creates all tables and indexes if they don't exist.

    Args:
        conn: DuckDB connection
    """
    for ddl in ALL_DDL:
        conn.execute(ddl)


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
