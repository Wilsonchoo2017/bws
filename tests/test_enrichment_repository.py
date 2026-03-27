"""Integration tests for enrichment repository with in-memory DuckDB."""

import pytest

from db.connection import get_memory_connection
from db.schema import init_schema
from services.enrichment.repository import (
    get_items_needing_enrichment,
    store_enrichment_result,
)
from services.enrichment.types import (
    EnrichmentResult,
    FieldResult,
    FieldStatus,
    MetadataField,
    SourceId,
)
from services.items.repository import get_or_create_item, get_item_detail


@pytest.fixture
def conn():
    """Create an in-memory DuckDB with schema initialized."""
    c = get_memory_connection()
    init_schema(c)
    return c


class TestGetItemsNeedingEnrichment:
    def test_finds_items_with_null_fields(self, conn):
        """Given items with NULL metadata. Then detected as needing enrichment."""
        get_or_create_item(conn, "75192")
        get_or_create_item(conn, "42151", title="Bugatti", year_released=2023)

        items = get_items_needing_enrichment(conn)
        set_numbers = [i["set_number"] for i in items]
        assert "75192" in set_numbers
        assert "42151" in set_numbers  # still missing theme, parts_count, etc.

    def test_excludes_fully_populated(self, conn):
        """Given fully populated item. Then not in results."""
        get_or_create_item(
            conn,
            "31009",
            title="Small Cottage",
            theme="Creator",
            year_released=2013,
            parts_count=271,
            image_url="https://example.com/31009.png",
        )

        items = get_items_needing_enrichment(conn)
        set_numbers = [i["set_number"] for i in items]
        assert "31009" not in set_numbers

    def test_respects_limit(self, conn):
        for i in range(10):
            get_or_create_item(conn, str(10000 + i))

        items = get_items_needing_enrichment(conn, limit=3)
        assert len(items) == 3


class TestStoreEnrichmentResult:
    def test_stores_found_fields(self, conn):
        """Given enrichment found title and year_released.
        Then stored in lego_items via COALESCE upsert."""
        get_or_create_item(conn, "75192")

        result = EnrichmentResult(
            set_number="75192",
            field_results=(
                FieldResult(
                    field=MetadataField.TITLE,
                    status=FieldStatus.FOUND,
                    value="Millennium Falcon",
                    source=SourceId.BRICKLINK,
                ),
                FieldResult(
                    field=MetadataField.YEAR_RELEASED,
                    status=FieldStatus.FOUND,
                    value=2017,
                    source=SourceId.BRICKLINK,
                ),
                FieldResult(
                    field=MetadataField.THEME,
                    status=FieldStatus.NOT_FOUND,
                ),
            ),
        )

        store_enrichment_result(conn, result)

        item = get_item_detail(conn, "75192")
        assert item is not None
        assert item["title"] == "Millennium Falcon"
        assert item["year_released"] == 2017
        assert item["theme"] is None  # NOT_FOUND fields not written

    def test_coalesce_preserves_existing(self, conn):
        """Given item already has title. Enrichment finds year_released.
        Then title preserved, year_released added."""
        get_or_create_item(conn, "75192", title="Existing Title")

        result = EnrichmentResult(
            set_number="75192",
            field_results=(
                FieldResult(
                    field=MetadataField.YEAR_RELEASED,
                    status=FieldStatus.FOUND,
                    value=2017,
                    source=SourceId.BRICKLINK,
                ),
            ),
        )

        store_enrichment_result(conn, result)

        item = get_item_detail(conn, "75192")
        assert item["title"] == "Existing Title"
        assert item["year_released"] == 2017

    def test_no_op_when_nothing_found(self, conn):
        """Given enrichment found nothing. Then no DB writes."""
        get_or_create_item(conn, "99999")

        result = EnrichmentResult(
            set_number="99999",
            field_results=(
                FieldResult(
                    field=MetadataField.YEAR_RELEASED,
                    status=FieldStatus.FAILED,
                    errors=("bricklink: HTTP 503",),
                ),
            ),
        )

        store_enrichment_result(conn, result)

        item = get_item_detail(conn, "99999")
        assert item["year_released"] is None

    def test_stores_year_retired_and_weight(self, conn):
        """Given enrichment found year_retired and weight (new columns).
        Then stored correctly."""
        get_or_create_item(conn, "31009")

        result = EnrichmentResult(
            set_number="31009",
            field_results=(
                FieldResult(
                    field=MetadataField.YEAR_RETIRED,
                    status=FieldStatus.FOUND,
                    value=2014,
                    source=SourceId.WORLDBRICKS,
                ),
                FieldResult(
                    field=MetadataField.WEIGHT,
                    status=FieldStatus.FOUND,
                    value="0.5 kg",
                    source=SourceId.BRICKLINK,
                ),
            ),
        )

        store_enrichment_result(conn, result)

        item = get_item_detail(conn, "31009")
        assert item["year_retired"] == 2014
        assert item["weight"] == "0.5 kg"
