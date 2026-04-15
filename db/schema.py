"""Database schema definitions for BWS.

Contains DDL for creating all required tables.
"""

import logging
from typing import Any

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
    wanted_count INTEGER,
    set_number VARCHAR GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED,
    watch_status VARCHAR DEFAULT 'active',
    scrape_interval_days INTEGER DEFAULT 7,
    last_scraped_at TIMESTAMPTZ,
    next_scrape_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

BRICKLINK_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS bricklink_price_history (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL,
    set_number VARCHAR GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED,
    six_month_new JSON,
    six_month_used JSON,
    current_new JSON,
    current_used JSON,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

BRICKLINK_MONTHLY_SALES_DDL = """
CREATE TABLE IF NOT EXISTS bricklink_monthly_sales (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL,
    set_number VARCHAR GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    condition VARCHAR NOT NULL,
    times_sold INTEGER,
    total_quantity INTEGER,
    min_price INTEGER,
    max_price INTEGER,
    avg_price INTEGER,
    currency VARCHAR DEFAULT 'USD',
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_id, year, month, condition)
);
"""

BRICKLINK_STORE_LISTINGS_DDL = """
CREATE TABLE IF NOT EXISTS bricklink_store_listings (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL,
    set_number VARCHAR GENERATED ALWAYS AS (SPLIT_PART(item_id, '-', 1)) STORED,
    store_id VARCHAR,
    store_name VARCHAR,
    seller_country_code VARCHAR,
    seller_country_name VARCHAR,
    condition VARCHAR,
    quantity INTEGER,
    price_cents INTEGER,
    currency VARCHAR,
    ships_to_viewer BOOLEAN,
    row_class_names VARCHAR,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    analyzed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_SCRAPE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS shopee_scrape_history (
    id INTEGER PRIMARY KEY,
    source_url VARCHAR NOT NULL,
    items_found INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    error VARCHAR,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_CAPTCHA_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS shopee_captcha_events (
    id INTEGER PRIMARY KEY,
    job_id VARCHAR,
    source_url VARCHAR NOT NULL,
    snapshot_dir VARCHAR NOT NULL,
    detection_reason VARCHAR NOT NULL,
    detection_signals JSONB,
    status VARCHAR NOT NULL DEFAULT 'pending',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolution_duration_s INTEGER,
    notes VARCHAR
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
    last_scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

MIGHTYUTAN_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS mightyutan_price_history (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL,
    price_myr VARCHAR NOT NULL,
    available BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

HOBBYDIGI_PRODUCTS_DDL = """
CREATE TABLE IF NOT EXISTS hobbydigi_products (
    id INTEGER PRIMARY KEY,
    product_id VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL,
    price_myr VARCHAR,
    original_price_myr VARCHAR,
    url VARCHAR,
    image_url VARCHAR,
    available BOOLEAN DEFAULT TRUE,
    rating_pct VARCHAR,
    tags VARCHAR,
    last_scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

HOBBYDIGI_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS hobbydigi_price_history (
    id INTEGER PRIMARY KEY,
    product_id VARCHAR NOT NULL,
    price_myr VARCHAR NOT NULL,
    available BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    last_scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

TOYSRUS_PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS toysrus_price_history (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL,
    price_myr VARCHAR NOT NULL,
    available BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    last_enriched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    txn_date TIMESTAMPTZ NOT NULL,
    notes VARCHAR,
    bill_id VARCHAR,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

MINIFIGURES_DDL = """
CREATE TABLE IF NOT EXISTS minifigures (
    id INTEGER PRIMARY KEY,
    minifig_id VARCHAR NOT NULL UNIQUE,
    name VARCHAR,
    image_url VARCHAR,
    year_released INTEGER,
    last_scraped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

SET_MINIFIGURES_DDL = """
CREATE TABLE IF NOT EXISTS set_minifigures (
    id INTEGER PRIMARY KEY,
    set_item_id VARCHAR NOT NULL,
    minifig_id VARCHAR NOT NULL,
    set_number VARCHAR GENERATED ALWAYS AS (SPLIT_PART(set_item_id, '-', 1)) STORED,
    quantity INTEGER DEFAULT 1,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
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
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    downloaded_at TIMESTAMPTZ,
    status VARCHAR DEFAULT 'pending',
    error VARCHAR,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_type, item_id)
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
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    locked_by VARCHAR,
    locked_at TIMESTAMPTZ,
    reason VARCHAR
);
"""

SCRAPE_TASK_ATTEMPTS_DDL = """
CREATE TABLE IF NOT EXISTS scrape_task_attempts (
    id INTEGER PRIMARY KEY,
    task_id VARCHAR NOT NULL,
    attempt_number INTEGER NOT NULL,
    error_category VARCHAR,
    error_message VARCHAR,
    duration_seconds FLOAT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

REDDIT_MENTIONS_DDL = """
CREATE TABLE IF NOT EXISTS reddit_mentions (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    subreddit VARCHAR NOT NULL,
    post_id VARCHAR NOT NULL,
    comment_id VARCHAR,
    created_at TIMESTAMPTZ NOT NULL,
    score INTEGER,
    num_comments INTEGER,
    author_hash VARCHAR,
    title VARCHAR,
    body_preview VARCHAR,
    permalink VARCHAR,
    is_comment BOOLEAN NOT NULL DEFAULT FALSE,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subreddit, post_id, comment_id, set_number)
);
"""

REDDIT_SCRAPE_CURSORS_DDL = """
CREATE TABLE IF NOT EXISTS reddit_scrape_cursors (
    subreddit VARCHAR NOT NULL,
    listing VARCHAR NOT NULL,
    last_fullname VARCHAR,
    last_created_utc TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    posts_seen INTEGER NOT NULL DEFAULT 0,
    mentions_saved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subreddit, listing)
);
"""

GOOGLE_TRENDS_THEME_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS google_trends_theme_snapshots (
    id INTEGER PRIMARY KEY,
    theme VARCHAR NOT NULL,
    theme_type VARCHAR NOT NULL DEFAULT 'generic',
    keyword_lego VARCHAR NOT NULL,
    keyword_bare VARCHAR NOT NULL DEFAULT '',
    search_property VARCHAR NOT NULL DEFAULT 'youtube',
    geo VARCHAR NOT NULL DEFAULT '',
    timeframe_start VARCHAR,
    timeframe_end VARCHAR,
    interest_lego_json VARCHAR,
    interest_bare_json VARCHAR,
    avg_lego FLOAT,
    avg_bare FLOAT,
    peak_lego INTEGER,
    peak_bare INTEGER,
    lego_share FLOAT,
    n_weeks INTEGER,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

KEEPA_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS keepa_snapshots (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    asin VARCHAR,
    title VARCHAR,
    keepa_url VARCHAR,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
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
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    title VARCHAR,
    theme VARCHAR,
    subtheme VARCHAR,
    year_released INTEGER,
    year_retired INTEGER,
    release_date DATE,
    retired_date DATE,
    pieces INTEGER,
    minifigs INTEGER,
    minifig_value_cents INTEGER,
    exclusive_minifigs BOOLEAN,
    availability VARCHAR,
    retiring_soon BOOLEAN,
    image_url VARCHAR,
    packaging VARCHAR,
    brickeconomy_url VARCHAR,
    upc VARCHAR,
    ean VARCHAR,
    designer VARCHAR,
    rrp_usd_cents INTEGER,
    rrp_gbp_cents INTEGER,
    rrp_eur_cents INTEGER,
    rrp_cad_cents INTEGER,
    rrp_aud_cents INTEGER,
    value_new_cents INTEGER,
    value_used_cents INTEGER,
    used_value_low_cents INTEGER,
    used_value_high_cents INTEGER,
    annual_growth_pct FLOAT,
    total_growth_pct FLOAT,
    rolling_growth_pct FLOAT,
    growth_90d_pct FLOAT,
    rating_value VARCHAR,
    review_count INTEGER,
    theme_rank INTEGER,
    subtheme_avg_growth_pct FLOAT,
    future_estimate_cents INTEGER,
    future_estimate_date VARCHAR,
    distribution_mean_cents INTEGER,
    distribution_stddev_cents INTEGER,
    value_chart_json JSON,
    sales_trend_json JSON,
    candlestick_json JSON
);
"""

ML_FEATURE_STORE_DDL = """
CREATE TABLE IF NOT EXISTS ml_feature_store (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    horizon_months INTEGER NOT NULL,
    snapshot_date TIMESTAMPTZ,
    target_return FLOAT,
    target_profitable BOOLEAN,
    features_json JSON NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(set_number, horizon_months)
);
"""

ML_MODEL_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS ml_model_runs (
    id INTEGER PRIMARY KEY,
    model_name VARCHAR NOT NULL,
    horizon_months INTEGER NOT NULL,
    task VARCHAR NOT NULL,
    r_squared FLOAT,
    roc_auc FLOAT,
    hit_rate FLOAT,
    quintile_spread FLOAT,
    n_train INTEGER,
    n_test INTEGER,
    feature_count INTEGER,
    artifact_path VARCHAR,
    trained_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_COMPETITION_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS shopee_competition_snapshots (
    id INTEGER PRIMARY KEY,
    set_number VARCHAR NOT NULL,
    listings_count INTEGER NOT NULL,
    unique_sellers INTEGER NOT NULL,
    total_sold_count INTEGER,
    min_price_cents INTEGER,
    max_price_cents INTEGER,
    avg_price_cents INTEGER,
    median_price_cents INTEGER,
    saturation_score FLOAT NOT NULL,
    saturation_level VARCHAR NOT NULL,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

SHOPEE_COMPETITION_LISTINGS_DDL = """
CREATE TABLE IF NOT EXISTS shopee_competition_listings (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,
    set_number VARCHAR NOT NULL,
    product_url VARCHAR NOT NULL,
    shop_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    price_cents INTEGER,
    price_display VARCHAR,
    sold_count_raw VARCHAR,
    sold_count_numeric INTEGER,
    rating VARCHAR,
    image_url VARCHAR,
    is_sold_out BOOLEAN DEFAULT FALSE,
    is_delisted BOOLEAN DEFAULT FALSE,
    discovery_method VARCHAR NOT NULL DEFAULT 'search',
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
"""

ML_PREDICTION_SNAPSHOTS_DDL = """
CREATE TABLE IF NOT EXISTS ml_prediction_snapshots (
    id INTEGER PRIMARY KEY DEFAULT nextval('ml_prediction_snapshots_id_seq'),
    snapshot_date DATE NOT NULL,
    set_number VARCHAR NOT NULL,
    predicted_growth_pct FLOAT NOT NULL,
    confidence VARCHAR,
    tier INTEGER,
    model_version VARCHAR,
    actual_growth_pct FLOAT,
    actual_measured_at DATE,
    UNIQUE (snapshot_date, set_number)
);
"""

SEQUENCES_DDL = """
CREATE SEQUENCE IF NOT EXISTS bricklink_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_monthly_sales_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_store_listings_id_seq;
CREATE SEQUENCE IF NOT EXISTS product_analysis_id_seq;
CREATE SEQUENCE IF NOT EXISTS minifigures_id_seq;
CREATE SEQUENCE IF NOT EXISTS set_minifigures_id_seq;
CREATE SEQUENCE IF NOT EXISTS minifig_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_saturation_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_scrape_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_captcha_events_id_seq;
CREATE SEQUENCE IF NOT EXISTS mightyutan_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS mightyutan_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS hobbydigi_products_id_seq;
CREATE SEQUENCE IF NOT EXISTS hobbydigi_price_history_id_seq;
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
CREATE SEQUENCE IF NOT EXISTS google_trends_theme_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS reddit_mentions_id_seq;
CREATE SEQUENCE IF NOT EXISTS scrape_tasks_id_seq;
CREATE SEQUENCE IF NOT EXISTS scrape_task_attempts_id_seq;
CREATE SEQUENCE IF NOT EXISTS ml_feature_store_id_seq;
CREATE SEQUENCE IF NOT EXISTS ml_model_runs_id_seq;
CREATE SEQUENCE IF NOT EXISTS ml_prediction_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_competition_snapshots_id_seq;
CREATE SEQUENCE IF NOT EXISTS shopee_competition_listings_id_seq;
"""

# Index creation statements
INDEXES_DDL = """
CREATE INDEX IF NOT EXISTS idx_bricklink_items_set_number
    ON bricklink_items(set_number);
CREATE INDEX IF NOT EXISTS idx_bricklink_price_history_set_number
    ON bricklink_price_history(set_number);
CREATE INDEX IF NOT EXISTS idx_bricklink_monthly_sales_set_number
    ON bricklink_monthly_sales(set_number);
CREATE INDEX IF NOT EXISTS idx_bricklink_store_listings_item_scraped
    ON bricklink_store_listings(item_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_bricklink_store_listings_set_number
    ON bricklink_store_listings(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_bricklink_store_listings_country
    ON bricklink_store_listings(seller_country_code);
CREATE INDEX IF NOT EXISTS idx_set_minifigures_set_number
    ON set_minifigures(set_number);
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
CREATE INDEX IF NOT EXISTS idx_set_minifigures_set
    ON set_minifigures(set_item_id);
CREATE INDEX IF NOT EXISTS idx_set_minifigures_minifig
    ON set_minifigures(minifig_id);
CREATE INDEX IF NOT EXISTS idx_minifig_price_history_item
    ON minifig_price_history(minifig_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_shopee_products_url
    ON shopee_products(product_url);
CREATE INDEX IF NOT EXISTS idx_shopee_products_source
    ON shopee_products(source_url);
CREATE INDEX IF NOT EXISTS idx_shopee_products_scraped
    ON shopee_products(scraped_at);
CREATE INDEX IF NOT EXISTS idx_shopee_saturation_set
    ON shopee_saturation(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_mightyutan_products_available
    ON mightyutan_products(available);
CREATE INDEX IF NOT EXISTS idx_mightyutan_price_history_sku
    ON mightyutan_price_history(sku, scraped_at);
CREATE INDEX IF NOT EXISTS idx_hobbydigi_products_available
    ON hobbydigi_products(available);
CREATE INDEX IF NOT EXISTS idx_hobbydigi_price_history_product_id
    ON hobbydigi_price_history(product_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_toysrus_products_available
    ON toysrus_products(available);
CREATE INDEX IF NOT EXISTS idx_toysrus_price_history_sku
    ON toysrus_price_history(sku, scraped_at);
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
CREATE INDEX IF NOT EXISTS idx_reddit_mentions_set_created
    ON reddit_mentions(set_number, created_at);
CREATE INDEX IF NOT EXISTS idx_reddit_mentions_subreddit_created
    ON reddit_mentions(subreddit, created_at);
CREATE INDEX IF NOT EXISTS idx_reddit_mentions_post
    ON reddit_mentions(subreddit, post_id);
CREATE INDEX IF NOT EXISTS idx_scrape_tasks_status_priority
    ON scrape_tasks(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_scrape_tasks_set_type
    ON scrape_tasks(set_number, task_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scrape_tasks_active_unique
    ON scrape_tasks(set_number, task_type)
    WHERE status IN ('pending', 'running', 'blocked');
CREATE INDEX IF NOT EXISTS idx_scrape_task_attempts_task_id
    ON scrape_task_attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_ml_feature_store_set
    ON ml_feature_store(set_number, horizon_months);
CREATE INDEX IF NOT EXISTS idx_ml_model_runs_trained
    ON ml_model_runs(trained_at);
CREATE INDEX IF NOT EXISTS idx_competition_snapshots_set
    ON shopee_competition_snapshots(set_number, scraped_at);
CREATE INDEX IF NOT EXISTS idx_competition_listings_snapshot
    ON shopee_competition_listings(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_competition_listings_set_url
    ON shopee_competition_listings(set_number, product_url, scraped_at);
CREATE INDEX IF NOT EXISTS idx_competition_listings_set_shop
    ON shopee_competition_listings(set_number, shop_id);
CREATE INDEX IF NOT EXISTS idx_shopee_captcha_events_status
    ON shopee_captcha_events(status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_shopee_captcha_events_job
    ON shopee_captcha_events(job_id);
CREATE INDEX IF NOT EXISTS idx_price_records_source_shopee
    ON price_records(set_number, recorded_at DESC)
    WHERE source = 'shopee';
CREATE INDEX IF NOT EXISTS idx_price_records_source_toysrus
    ON price_records(set_number, recorded_at DESC)
    WHERE source = 'toysrus';
CREATE INDEX IF NOT EXISTS idx_price_records_source_mightyutan
    ON price_records(set_number, recorded_at DESC)
    WHERE source = 'mightyutan';
CREATE INDEX IF NOT EXISTS idx_price_records_source_hobbydigi
    ON price_records(set_number, recorded_at DESC)
    WHERE source = 'hobbydigi';
CREATE INDEX IF NOT EXISTS idx_price_records_source_bricklink_new
    ON price_records(set_number, recorded_at DESC)
    WHERE source = 'bricklink_new';
CREATE INDEX IF NOT EXISTS idx_price_records_source_bricklink_used
    ON price_records(set_number, recorded_at DESC)
    WHERE source = 'bricklink_used';
CREATE INDEX IF NOT EXISTS idx_scrape_tasks_pending_type
    ON scrape_tasks(task_type, created_at)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_bricklink_monthly_sales_new
    ON bricklink_monthly_sales(item_id, year, month)
    WHERE condition = 'N';
"""

ALL_DDL = [
    SEQUENCES_DDL,
    BRICKLINK_ITEMS_DDL,
    BRICKLINK_PRICE_HISTORY_DDL,
    BRICKLINK_MONTHLY_SALES_DDL,
    BRICKLINK_STORE_LISTINGS_DDL,
    PRODUCT_ANALYSIS_DDL,
    IMAGE_ASSETS_DDL,
    MINIFIGURES_DDL,
    SET_MINIFIGURES_DDL,
    MINIFIG_PRICE_HISTORY_DDL,
    SHOPEE_PRODUCTS_DDL,
    SHOPEE_SATURATION_DDL,
    SHOPEE_SCRAPE_HISTORY_DDL,
    SHOPEE_CAPTCHA_EVENTS_DDL,
    MIGHTYUTAN_PRODUCTS_DDL,
    MIGHTYUTAN_PRICE_HISTORY_DDL,
    HOBBYDIGI_PRODUCTS_DDL,
    HOBBYDIGI_PRICE_HISTORY_DDL,
    TOYSRUS_PRODUCTS_DDL,
    TOYSRUS_PRICE_HISTORY_DDL,
    LEGO_ITEMS_DDL,
    PRICE_RECORDS_DDL,
    PORTFOLIO_TRANSACTIONS_DDL,
    PORTFOLIO_SNAPSHOTS_DDL,
    BRICKECONOMY_SNAPSHOTS_DDL,
    KEEPA_SNAPSHOTS_DDL,
    GOOGLE_TRENDS_SNAPSHOTS_DDL,
    GOOGLE_TRENDS_THEME_SNAPSHOTS_DDL,
    REDDIT_MENTIONS_DDL,
    REDDIT_SCRAPE_CURSORS_DDL,
    SCRAPE_TASKS_DDL,
    SCRAPE_TASK_ATTEMPTS_DDL,
    ML_FEATURE_STORE_DDL,
    ML_MODEL_RUNS_DDL,
    ML_PREDICTION_SNAPSHOTS_DDL,
    SHOPEE_COMPETITION_SNAPSHOTS_DDL,
    SHOPEE_COMPETITION_LISTINGS_DDL,
    INDEXES_DDL,
]


def _migrate_bricklink_items(conn: Any) -> None:
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


def _migrate_lego_items(conn: Any) -> None:
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
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN retiring_soon BOOLEAN DEFAULT FALSE"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lego_items_set_number "
            "ON lego_items(set_number)"
        )
    if "last_enriched_at" not in existing:
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN last_enriched_at TIMESTAMPTZ"
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
    if "listing_price_cents" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN listing_price_cents INTEGER")
    if "listing_currency" not in existing:
        conn.execute(
            "ALTER TABLE lego_items ADD COLUMN listing_currency VARCHAR DEFAULT 'MYR'"
        )
    if "release_date" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN release_date DATE")
    if "retired_date" not in existing:
        conn.execute("ALTER TABLE lego_items ADD COLUMN retired_date DATE")


def _migrate_brickeconomy_snapshots(conn: Any) -> None:
    """Add missing columns to brickeconomy_snapshots."""
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'brickeconomy_snapshots'"
        ).fetchall()
    }
    _new_columns: list[tuple[str, str]] = [
        ("year_retired", "INTEGER"),
        ("retiring_soon", "BOOLEAN"),
        ("release_date", "DATE"),
        ("retired_date", "DATE"),
        ("minifig_value_cents", "INTEGER"),
        ("exclusive_minifigs", "BOOLEAN"),
        ("upc", "VARCHAR"),
        ("ean", "VARCHAR"),
        ("designer", "VARCHAR"),
        ("rrp_cad_cents", "INTEGER"),
        ("rrp_aud_cents", "INTEGER"),
        ("used_value_low_cents", "INTEGER"),
        ("used_value_high_cents", "INTEGER"),
        ("total_growth_pct", "FLOAT"),
        ("rolling_growth_pct", "FLOAT"),
        ("growth_90d_pct", "FLOAT"),
        ("theme_rank", "INTEGER"),
        ("subtheme_avg_growth_pct", "FLOAT"),
        ("packaging", "VARCHAR"),
    ]
    for col_name, col_type in _new_columns:
        if col_name not in existing:
            conn.execute(
                f"ALTER TABLE brickeconomy_snapshots ADD COLUMN {col_name} {col_type}"
            )


def _migrate_ml_prediction_snapshots(conn: Any) -> None:
    """Add richer prediction fields to ml_prediction_snapshots."""
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ml_prediction_snapshots'"
        ).fetchall()
    }
    _new_columns: list[tuple[str, str]] = [
        ("avoid_probability", "FLOAT"),
        ("buy_signal", "BOOLEAN"),
        ("kelly_fraction", "FLOAT"),
        ("win_probability", "FLOAT"),
        ("interval_lower", "FLOAT"),
        ("interval_upper", "FLOAT"),
    ]
    for col_name, col_type in _new_columns:
        if col_name not in existing:
            conn.execute(
                f"ALTER TABLE ml_prediction_snapshots ADD COLUMN {col_name} {col_type}"
            )


def _migrate_scrape_tasks(conn: Any) -> None:
    """Add reason column to scrape_tasks."""
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'scrape_tasks'"
        ).fetchall()
    }
    if "reason" not in existing:
        conn.execute("ALTER TABLE scrape_tasks ADD COLUMN reason VARCHAR")


def _migrate_shopee_products(conn: Any) -> None:
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


def _migrate_bricklink_set_number(conn: Any) -> None:
    """Add set_number generated columns to BrickLink tables and set_minifigures.

    These columns auto-extract the bare set number from item_id (e.g. '75192-1' -> '75192').
    Safe to run multiple times -- skips if column already exists.
    """
    _table_source_map = [
        ("bricklink_items", "item_id"),
        ("bricklink_price_history", "item_id"),
        ("bricklink_monthly_sales", "item_id"),
        ("set_minifigures", "set_item_id"),
    ]
    for table, source_col in _table_source_map:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}'"  # noqa: S608
            ).fetchall()
        }
        if "set_number" not in existing:
            try:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN set_number VARCHAR "  # noqa: S608
                    f"GENERATED ALWAYS AS (SPLIT_PART({source_col}, '-', 1)) STORED"
                )
                logger.info("Added set_number generated column to %s", table)
            except Exception:  # noqa: BLE001
                logger.debug("set_number migration skipped for %s", table)


def _migrate_date_columns(conn: Any) -> None:
    """Convert retired_date/release_date from VARCHAR to DATE.

    Existing data is 'YYYY-MM' format; appends '-01' during conversion.
    Safe to run multiple times -- skips if columns are already DATE type.
    """
    _conversions = [
        ("lego_items", "retired_date"),
        ("lego_items", "release_date"),
        ("brickeconomy_snapshots", "retired_date"),
        ("brickeconomy_snapshots", "release_date"),
    ]
    for table, col in _conversions:
        try:
            row = conn.execute(
                "SELECT data_type FROM information_schema.columns "
                f"WHERE table_name = '{table}' AND column_name = '{col}'"  # noqa: S608
            ).fetchone()
            if row and row[0] in ("character varying", "text"):
                conn.execute(
                    f"ALTER TABLE {table} "  # noqa: S608
                    f"ALTER COLUMN {col} TYPE DATE "
                    f"USING CASE "
                    f"  WHEN {col} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$' "
                    f"    THEN {col}::DATE "
                    f"  WHEN {col} ~ '^\\d{{4}}-\\d{{2}}$' "
                    f"    THEN ({col} || '-01')::DATE "
                    f"  ELSE NULL "
                    f"END"
                )
                logger.info("Converted %s.%s from VARCHAR to DATE", table, col)
        except Exception:  # noqa: BLE001
            logger.debug("Date migration skipped for %s.%s", table, col)


def _migrate_timestamp_to_timestamptz(conn: Any) -> None:
    """Convert TIMESTAMP columns to TIMESTAMPTZ.

    This is a metadata-only change in PostgreSQL (no data rewrite).
    Safe to run multiple times -- skips if already TIMESTAMPTZ.
    """
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "  AND data_type = 'timestamp without time zone'"
    ).fetchall()
    for table_name, column_name in rows:
        try:
            conn.execute(
                f"ALTER TABLE {table_name} "  # noqa: S608
                f"ALTER COLUMN {column_name} TYPE TIMESTAMPTZ"
            )
            logger.info("Converted %s.%s to TIMESTAMPTZ", table_name, column_name)
        except Exception:  # noqa: BLE001
            logger.debug(
                "TIMESTAMPTZ migration skipped for %s.%s", table_name, column_name
            )


def _drop_redundant_indexes(conn: Any) -> None:
    """Drop indexes that duplicate UNIQUE constraints."""
    redundant = [
        "idx_lego_items_set_number",
        "idx_mightyutan_products_sku",
        "idx_toysrus_products_sku",
        "idx_minifigures_minifig_id",
    ]
    for idx_name in redundant:
        try:
            conn.execute(f"DROP INDEX IF EXISTS {idx_name}")  # noqa: S608
        except Exception:  # noqa: BLE001
            logger.debug("Could not drop index %s", idx_name)


_SEQUENCE_TABLE_MAP = [
    ("bricklink_items_id_seq", "bricklink_items"),
    ("bricklink_price_history_id_seq", "bricklink_price_history"),
    ("bricklink_monthly_sales_id_seq", "bricklink_monthly_sales"),
    ("bricklink_store_listings_id_seq", "bricklink_store_listings"),
    ("product_analysis_id_seq", "product_analysis"),
    ("minifigures_id_seq", "minifigures"),
    ("set_minifigures_id_seq", "set_minifigures"),
    ("minifig_price_history_id_seq", "minifig_price_history"),
    ("shopee_products_id_seq", "shopee_products"),
    ("shopee_saturation_id_seq", "shopee_saturation"),
    ("shopee_scrape_history_id_seq", "shopee_scrape_history"),
    ("shopee_captcha_events_id_seq", "shopee_captcha_events"),
    ("mightyutan_products_id_seq", "mightyutan_products"),
    ("mightyutan_price_history_id_seq", "mightyutan_price_history"),
    ("hobbydigi_products_id_seq", "hobbydigi_products"),
    ("hobbydigi_price_history_id_seq", "hobbydigi_price_history"),
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
    ("google_trends_theme_snapshots_id_seq", "google_trends_theme_snapshots"),
    ("reddit_mentions_id_seq", "reddit_mentions"),
    ("scrape_tasks_id_seq", "scrape_tasks"),
    ("scrape_task_attempts_id_seq", "scrape_task_attempts"),
    ("ml_feature_store_id_seq", "ml_feature_store"),
    ("ml_model_runs_id_seq", "ml_model_runs"),
    ("shopee_competition_snapshots_id_seq", "shopee_competition_snapshots"),
    ("shopee_competition_listings_id_seq", "shopee_competition_listings"),
]


def _set_sequence_defaults(conn: Any) -> None:
    """Ensure id columns use sequence defaults for auto-generation.

    Without DEFAULT, omitting id from INSERT causes a NOT NULL violation,
    and concurrent nextval() calls can produce PK collisions.
    """
    for seq_name, table_name in _SEQUENCE_TABLE_MAP:
        try:
            conn.execute(
                f"ALTER TABLE {table_name} "  # noqa: S608
                f"ALTER COLUMN id SET DEFAULT nextval('{seq_name}')"
            )
        except Exception:  # noqa: BLE001
            logger.debug("Could not set default for %s.id", table_name)


def _sync_sequences(conn: Any) -> None:
    """Sync all sequences to max(id) + 1 of their tables.

    Prevents primary key collisions when sequences fall behind
    existing data (e.g., after restores or manual inserts).
    """
    for seq_name, table_name in _SEQUENCE_TABLE_MAP:
        try:
            row = conn.execute(
                f"SELECT COALESCE(MAX(id), 0) FROM {table_name}"  # noqa: S608
            ).fetchone()
            max_id = row[0] if row else 0
            start = max_id + 1 if max_id > 0 else 1

            conn.execute(
                f"ALTER SEQUENCE {seq_name} RESTART WITH {start}"  # noqa: S608
            )
        except Exception:  # noqa: BLE001
            # Table or sequence may not exist yet on first init
            logger.debug("Sequence sync skipped for %s: table not ready", seq_name)


def init_schema(conn: Any) -> None:
    """Initialize the database schema.

    Creates all tables and indexes if they don't exist.
    """
    for ddl in ALL_DDL:
        conn.execute(ddl)
    _migrate_bricklink_items(conn)
    _migrate_bricklink_set_number(conn)
    _migrate_lego_items(conn)
    _migrate_brickeconomy_snapshots(conn)
    _migrate_ml_prediction_snapshots(conn)
    _migrate_scrape_tasks(conn)
    _migrate_shopee_products(conn)
    _migrate_timestamp_to_timestamptz(conn)
    _migrate_date_columns(conn)
    _drop_redundant_indexes(conn)
    _set_sequence_defaults(conn)
    _sync_sequences(conn)


def drop_all_tables(conn: Any) -> None:
    """Drop all tables (for testing/reset)."""
    conn.execute("DROP TABLE IF EXISTS product_analysis;")
    conn.execute("DROP TABLE IF EXISTS bricklink_monthly_sales;")
    conn.execute("DROP TABLE IF EXISTS bricklink_price_history;")
    conn.execute("DROP TABLE IF EXISTS bricklink_items;")
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
    conn.execute("DROP TABLE IF EXISTS scrape_task_attempts;")
    conn.execute("DROP SEQUENCE IF EXISTS scrape_task_attempts_id_seq;")
    conn.execute("DROP TABLE IF EXISTS scrape_tasks;")
    conn.execute("DROP SEQUENCE IF EXISTS scrape_tasks_id_seq;")
    conn.execute("DROP TABLE IF EXISTS ml_feature_store;")
    conn.execute("DROP SEQUENCE IF EXISTS ml_feature_store_id_seq;")
    conn.execute("DROP TABLE IF EXISTS ml_model_runs;")
    conn.execute("DROP SEQUENCE IF EXISTS ml_model_runs_id_seq;")


def get_table_stats(conn: Any) -> dict[str, int]:
    """Get row counts for all tables."""
    tables = [
        "bricklink_items",
        "bricklink_price_history",
        "bricklink_monthly_sales",
        "product_analysis",
        "minifigures",
        "set_minifigures",
        "minifig_price_history",
        "portfolio_transactions",
        "portfolio_snapshots",
        "image_assets",
        "brickeconomy_snapshots",
        "keepa_snapshots",
        "google_trends_snapshots",
        "google_trends_theme_snapshots",
        "reddit_mentions",
        "scrape_tasks",
        "shopee_competition_snapshots",
        "shopee_competition_listings",
    ]
    stats = {}
    for table in tables:
        try:
            result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
            stats[table] = result[0] if result else 0
        except Exception:  # noqa: BLE001
            stats[table] = 0
    return stats
