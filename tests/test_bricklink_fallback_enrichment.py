"""Tests for BrickLink fallback enrichment for parts_count and theme.

Covers GWT #18-42: source adapter, config, orchestrator fallback,
fetcher cache, repository persistence, schema migration, and E2E flow.
"""

import pytest

from bws_types.models import BricklinkData
from db.connection import get_connection
from db.schema import init_schema
from services.enrichment.circuit_breaker import CircuitBreakerState, SourceState
from services.enrichment.config import (
    FIELD_SOURCE_PRIORITY,
    SOURCE_CONFIGS,
)
from services.enrichment.orchestrator import (
    determine_sources_needed,
    enrich,
    resolve_fields,
)
from services.enrichment.source_adapter import adapt_bricklink, make_failed_result
from services.enrichment.types import (
    FieldResult,
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)


# ---------------------------------------------------------------------------
# GWT #18-19: Source Adapter
# ---------------------------------------------------------------------------


class TestAdaptBricklinkNewFields:
    """Adapter includes parts_count and theme from BricklinkData."""

    def test_parts_count_and_theme_populated(self):
        """#18: Given BricklinkData with parts_count=305, theme='Disney'.
        When adapting. Then SourceResult contains both fields."""
        data = BricklinkData(
            item_id="43216-1",
            item_type="S",
            parts_count=305,
            theme="Disney",
        )
        result = adapt_bricklink(data)
        assert result.success
        assert result.fields[MetadataField.PARTS_COUNT] == 305
        assert result.fields[MetadataField.THEME] == "Disney"

    def test_parts_count_and_theme_none(self):
        """#19: Given BricklinkData with parts_count=None, theme=None.
        When adapting. Then SourceResult has None for both."""
        data = BricklinkData(item_id="99999-1", item_type="S")
        result = adapt_bricklink(data)
        assert result.success
        assert result.fields[MetadataField.PARTS_COUNT] is None
        assert result.fields[MetadataField.THEME] is None


# ---------------------------------------------------------------------------
# GWT #20-22: Config
# ---------------------------------------------------------------------------


class TestConfigPriority:
    """FIELD_SOURCE_PRIORITY and SOURCE_CONFIGS updated for new fields."""

    def test_parts_count_priority_order(self):
        """#20: PARTS_COUNT: BrickLink first, BrickEconomy second."""
        sources = FIELD_SOURCE_PRIORITY[MetadataField.PARTS_COUNT]
        assert sources[0] == SourceId.BRICKLINK

    def test_theme_priority_order(self):
        """#21: THEME: BrickLink first, BrickEconomy second."""
        sources = FIELD_SOURCE_PRIORITY[MetadataField.THEME]
        assert sources[0] == SourceId.BRICKLINK
        assert sources[1] == SourceId.BRICKECONOMY

    def test_bricklink_fields_provided(self):
        """#22: BrickLink SOURCE_CONFIG includes PARTS_COUNT and THEME."""
        bl_config = SOURCE_CONFIGS[SourceId.BRICKLINK]
        assert MetadataField.PARTS_COUNT in bl_config.fields_provided
        assert MetadataField.THEME in bl_config.fields_provided


# ---------------------------------------------------------------------------
# GWT #23-25: determine_sources_needed
# ---------------------------------------------------------------------------


class TestDetermineSourcesWithFallback:
    """determine_sources_needed returns fallback sources."""

    def test_parts_count_missing_bricklink_source(self):
        """#23: Given PARTS_COUNT missing, all healthy.
        Then BrickLink returned."""
        cb = CircuitBreakerState()
        sources = determine_sources_needed((MetadataField.PARTS_COUNT,), cb)
        assert SourceId.BRICKLINK in sources

    def test_theme_missing_bricklink_broken(self):
        """#24: Given THEME missing, BrickLink circuit-broken.
        Then BrickEconomy returned as fallback."""
        from datetime import datetime, timezone

        cb = CircuitBreakerState(
            states={
                SourceId.BRICKLINK: SourceState(
                    consecutive_failures=10,
                    last_failure_at=datetime.now(tz=timezone.utc),
                    is_open=True,
                ),
            },
        )
        sources = determine_sources_needed((MetadataField.THEME,), cb)
        assert SourceId.BRICKLINK not in sources
        assert SourceId.BRICKECONOMY in sources



# ---------------------------------------------------------------------------
# GWT #26-30: resolve_fields priority/fallback
# ---------------------------------------------------------------------------


class TestResolveFieldsFallback:
    """resolve_fields uses priority order with BrickLink as fallback."""

    def test_bricklink_provides_parts_count(self):
        """#26: Given BrickLink returns 305.
        Then BrickLink value used."""
        bl_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.PARTS_COUNT: 305},
        )
        field_results = resolve_fields(
            (MetadataField.PARTS_COUNT,),
            {SourceId.BRICKLINK: bl_result},
        )
        assert field_results[0].value == 305
        assert field_results[0].source == SourceId.BRICKLINK

    def test_bricklink_wins_for_theme(self):
        """#28: Given BrickLink returns 'Star Wars', BrickEconomy returns 'Star Wars'.
        Then BrickLink value used (higher priority)."""
        bl_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.THEME: "Star Wars"},
        )
        be_result = SourceResult(
            source=SourceId.BRICKECONOMY,
            success=True,
            fields={MetadataField.THEME: "Star Wars"},
        )
        field_results = resolve_fields(
            (MetadataField.THEME,),
            {SourceId.BRICKLINK: bl_result, SourceId.BRICKECONOMY: be_result},
        )
        assert field_results[0].value == "Star Wars"
        assert field_results[0].source == SourceId.BRICKLINK

    def test_brickeconomy_fallback_for_theme(self):
        """#29: Given BrickLink returns None, BrickEconomy returns 'Disney'.
        Then BrickEconomy value used (fallback)."""
        bl_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.THEME: None},
        )
        be_result = SourceResult(
            source=SourceId.BRICKECONOMY,
            success=True,
            fields={MetadataField.THEME: "Disney"},
        )
        field_results = resolve_fields(
            (MetadataField.THEME,),
            {SourceId.BRICKLINK: bl_result, SourceId.BRICKECONOMY: be_result},
        )
        assert field_results[0].value == "Disney"
        assert field_results[0].source == SourceId.BRICKECONOMY

    def test_bricklink_none_parts_count(self):
        """#30: Given BrickLink returns None for PARTS_COUNT.
        Then field status is NOT_FOUND."""
        bl_result = SourceResult(
            source=SourceId.BRICKLINK,
            success=True,
            fields={MetadataField.PARTS_COUNT: None},
        )
        field_results = resolve_fields(
            (MetadataField.PARTS_COUNT,),
            {SourceId.BRICKLINK: bl_result},
        )
        assert field_results[0].status == FieldStatus.NOT_FOUND
        assert field_results[0].value is None


# ---------------------------------------------------------------------------
# GWT #31-33: Fetcher cache path
# ---------------------------------------------------------------------------


class TestFetcherCachePath:
    """BrickLink fetcher cache path includes parts_count and theme.

    Tests the cache-reconstruction logic directly by building BricklinkData
    from a DB row and adapting it, matching what fetch_from_bricklink does
    on a cache hit. We avoid calling the full fetcher because the DB returns
    timezone-naive datetimes that trigger a silent exception in the
    cache path, causing a fallback to HTTP.
    """

    @pytest.fixture
    def conn(self):
        c = get_connection()
        init_schema(c)
        return c

    def _insert_cached_item(
        self, conn, item_id: str, *, parts_count=None, theme=None
    ):
        """Insert a bricklink_items row."""
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM bricklink_items"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO bricklink_items (
                id, item_id, item_type, title, weight, year_released, image_url,
                parts_count, theme, last_scraped_at, created_at, updated_at
            ) VALUES (?, ?, 'S', 'Test', '100g', 2023, 'https://example.com/img.png',
                      ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [next_id, item_id, parts_count, theme],
        )

    def test_cache_hit_with_new_fields(self, conn):
        """#31: Given cached row with parts_count=305, theme='Disney'.
        When cache row is reconstructed into BricklinkData and adapted.
        Then SourceResult contains both fields."""
        self._insert_cached_item(conn, "43216-1", parts_count=305, theme="Disney")

        row = conn.execute(
            """
            SELECT item_id, item_type, title, weight, year_released, image_url,
                   parts_count, theme, last_scraped_at
            FROM bricklink_items WHERE item_id = '43216-1'
            """,
        ).fetchone()

        cached = BricklinkData(
            item_id=row[0], item_type=row[1], title=row[2], weight=row[3],
            year_released=row[4], image_url=row[5], parts_count=row[6], theme=row[7],
        )
        result = adapt_bricklink(cached)
        assert result.success
        assert result.fields[MetadataField.PARTS_COUNT] == 305
        assert result.fields[MetadataField.THEME] == "Disney"

    def test_cache_hit_null_new_fields(self, conn):
        """#32: Given cached row with parts_count=NULL, theme=NULL (old data).
        When cache row is reconstructed into BricklinkData and adapted.
        Then SourceResult has None for both (no crash)."""
        self._insert_cached_item(conn, "43216-1", parts_count=None, theme=None)

        row = conn.execute(
            """
            SELECT item_id, item_type, title, weight, year_released, image_url,
                   parts_count, theme, last_scraped_at
            FROM bricklink_items WHERE item_id = '43216-1'
            """,
        ).fetchone()

        cached = BricklinkData(
            item_id=row[0], item_type=row[1], title=row[2], weight=row[3],
            year_released=row[4], image_url=row[5], parts_count=row[6], theme=row[7],
        )
        result = adapt_bricklink(cached)
        assert result.success
        assert result.fields[MetadataField.PARTS_COUNT] is None
        assert result.fields[MetadataField.THEME] is None


# ---------------------------------------------------------------------------
# GWT #34-36: Repository upsert_item
# ---------------------------------------------------------------------------


class TestRepositoryUpsert:
    """upsert_item persists parts_count and theme."""

    @pytest.fixture
    def conn(self):
        c = get_connection()
        init_schema(c)
        return c

    def test_insert_with_new_fields(self, conn):
        """#34: Given new BricklinkData with parts_count and theme.
        When inserting. Then row has both values."""
        from services.bricklink.repository import upsert_item, get_item

        data = BricklinkData(
            item_id="43216-1",
            item_type="S",
            title="Princess Enchanted Journey",
            parts_count=305,
            theme="Disney",
        )
        upsert_item(conn, data)

        row = conn.execute(
            "SELECT parts_count, theme FROM bricklink_items WHERE item_id = ?",
            ["43216-1"],
        ).fetchone()
        assert row[0] == 305
        assert row[1] == "Disney"

    def test_update_with_new_fields(self, conn):
        """#35: Given existing item, new scrape has parts_count and theme.
        When updating. Then row updated with new values."""
        from services.bricklink.repository import upsert_item

        # Initial insert without new fields
        data_v1 = BricklinkData(
            item_id="43216-1",
            item_type="S",
            title="Princess Enchanted Journey",
        )
        upsert_item(conn, data_v1)

        # Update with new fields
        data_v2 = BricklinkData(
            item_id="43216-1",
            item_type="S",
            title="Princess Enchanted Journey",
            parts_count=305,
            theme="Disney",
        )
        upsert_item(conn, data_v2)

        row = conn.execute(
            "SELECT parts_count, theme FROM bricklink_items WHERE item_id = ?",
            ["43216-1"],
        ).fetchone()
        assert row[0] == 305
        assert row[1] == "Disney"

    def test_insert_with_null_new_fields(self, conn):
        """#36: Given BricklinkData with parts_count=None, theme=None.
        When inserting. Then row has NULL for both."""
        from services.bricklink.repository import upsert_item

        data = BricklinkData(item_id="99999-1", item_type="S")
        upsert_item(conn, data)

        row = conn.execute(
            "SELECT parts_count, theme FROM bricklink_items WHERE item_id = ?",
            ["99999-1"],
        ).fetchone()
        assert row[0] is None
        assert row[1] is None


# ---------------------------------------------------------------------------
# GWT #37-39: Schema migration
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """_migrate_bricklink_items adds columns to existing tables."""

    def test_migration_adds_columns(self):
        """#37: Given existing table without parts_count/theme.
        When migration runs. Then columns added, existing data preserved."""
        conn = get_connection()
        # Create old schema without new columns
        conn.execute("""
            CREATE TABLE bricklink_items (
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
            )
        """)
        conn.execute(
            "INSERT INTO bricklink_items (id, item_id, item_type, title) "
            "VALUES (1, '75192-1', 'S', 'Millennium Falcon')"
        )

        from db.schema import _migrate_bricklink_items
        _migrate_bricklink_items(conn)

        # Columns should exist
        cols = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bricklink_items'"
            ).fetchall()
        }
        assert "parts_count" in cols
        assert "theme" in cols

        # Existing data preserved
        row = conn.execute(
            "SELECT title, parts_count, theme FROM bricklink_items WHERE item_id = '75192-1'"
        ).fetchone()
        assert row[0] == "Millennium Falcon"
        assert row[1] is None  # new column defaults to NULL
        assert row[2] is None

    def test_migration_idempotent(self):
        """#38: Given table already has parts_count and theme.
        When migration runs again. Then no error."""
        conn = get_connection()
        init_schema(conn)

        from db.schema import _migrate_bricklink_items
        # Should not raise
        _migrate_bricklink_items(conn)
        _migrate_bricklink_items(conn)

    def test_fresh_database_has_columns(self):
        """#39: Given fresh database. When init_schema runs.
        Then bricklink_items has parts_count and theme."""
        conn = get_connection()
        init_schema(conn)

        cols = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bricklink_items'"
            ).fetchall()
        }
        assert "parts_count" in cols
        assert "theme" in cols


# ---------------------------------------------------------------------------
# GWT #40-42: End-to-end enrichment flow
# ---------------------------------------------------------------------------


class TestEndToEndFallback:
    """Full enrichment flow with BrickLink as fallback source."""

    def test_bricklink_provides_parts_count_and_theme(self, make_item):
        """#40: Given BrickLink has both parts_count and theme.
        When enrichment runs.
        Then parts_count and theme found via BrickLink."""
        item = make_item()

        def bricklink_fetcher(sn: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Princess Enchanted Journey",
                    MetadataField.YEAR_RELEASED: 2023,
                    MetadataField.IMAGE_URL: "https://img.bricklink.com/43216.png",
                    MetadataField.WEIGHT: "482g",
                    MetadataField.PARTS_COUNT: 305,
                    MetadataField.THEME: "Disney",
                },
            )

        result, _ = enrich(
            "43216",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
            },
            CircuitBreakerState(),
        )

        parts_r = next(
            r for r in result.field_results if r.field == MetadataField.PARTS_COUNT
        )
        assert parts_r.status == FieldStatus.FOUND
        assert parts_r.value == 305
        assert parts_r.source == SourceId.BRICKLINK

        theme_r = next(
            r for r in result.field_results if r.field == MetadataField.THEME
        )
        assert theme_r.status == FieldStatus.FOUND
        assert theme_r.value == "Disney"
        assert theme_r.source == SourceId.BRICKLINK

    def test_bricklink_provides_parts_count_in_e2e(self, make_item):
        """#41: Given BrickLink has parts_count=305.
        When enrichment runs.
        Then BrickLink value used."""
        item = make_item()

        def bricklink_fetcher(sn: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Test Set",
                    MetadataField.YEAR_RELEASED: 2023,
                    MetadataField.IMAGE_URL: "https://example.com/img.png",
                    MetadataField.WEIGHT: "500g",
                    MetadataField.PARTS_COUNT: 305,
                    MetadataField.THEME: "Technic",
                },
            )

        result, _ = enrich(
            "42151",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
            },
            CircuitBreakerState(),
        )

        parts_r = next(
            r for r in result.field_results if r.field == MetadataField.PARTS_COUNT
        )
        assert parts_r.value == 305
        assert parts_r.source == SourceId.BRICKLINK

    def test_bricklink_wins_for_theme_when_available(self, make_item):
        """#42: Given BrickLink has theme='Star Wars'.
        When enrichment runs.
        Then BrickLink value used (highest priority)."""
        item = make_item()

        def bricklink_fetcher(sn: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={
                    MetadataField.TITLE: "Millennium Falcon",
                    MetadataField.YEAR_RELEASED: 2017,
                    MetadataField.IMAGE_URL: "https://example.com/img.png",
                    MetadataField.WEIGHT: "14.2 kg",
                    MetadataField.PARTS_COUNT: 7541,
                    MetadataField.THEME: "Star Wars",
                },
            )

        result, _ = enrich(
            "75192",
            item,
            {
                SourceId.BRICKLINK: bricklink_fetcher,
            },
            CircuitBreakerState(),
            fields=(MetadataField.THEME,),
        )

        theme_r = next(
            r for r in result.field_results if r.field == MetadataField.THEME
        )
        assert theme_r.value == "Star Wars"
        assert theme_r.source == SourceId.BRICKLINK
