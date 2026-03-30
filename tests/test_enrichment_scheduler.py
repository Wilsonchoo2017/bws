"""Tests for the periodic enrichment sweep scheduler."""

import asyncio

import pytest

from api.jobs import JobManager
from api.schemas import JobStatus
from db.connection import get_memory_connection
from db.schema import init_schema
from services.items.repository import get_or_create_item, record_price


@pytest.fixture
def conn():
    c = get_memory_connection()
    init_schema(c)
    return c


@pytest.fixture
def manager():
    return JobManager()


class TestEnrichmentSweep:
    """Integration tests for the enrichment sweep."""

    def test_sweep_queues_jobs_for_incomplete_items(self, conn, manager):
        """Given items with missing metadata in DB.
        When sweep runs.
        Then enrichment jobs are queued for those items."""
        from services.enrichment.auto import queue_enrichment_batch
        from services.enrichment.repository import get_items_needing_enrichment

        # Create items with missing metadata (need price records to pass EXISTS filter)
        get_or_create_item(conn, "75192")
        record_price(conn, "75192", source="toysrus", price_cents=329900, currency="MYR")
        get_or_create_item(conn, "42151", title="Bugatti")
        record_price(conn, "42151", source="shopee", price_cents=24900, currency="MYR")

        items = get_items_needing_enrichment(conn, limit=10)
        set_numbers = [item["set_number"] for item in items]
        queued = queue_enrichment_batch(manager, set_numbers)

        assert queued == 2
        jobs = manager.list_jobs()
        enrichment_jobs = [j for j in jobs if j.scraper_id == "enrichment"]
        assert len(enrichment_jobs) == 2

    def test_sweep_skips_fully_populated(self, conn, manager):
        """Given fully populated item.
        When sweep runs.
        Then no job queued for it."""
        from services.enrichment.auto import queue_enrichment_batch
        from services.enrichment.repository import get_items_needing_enrichment

        get_or_create_item(
            conn,
            "31009",
            title="Small Cottage",
            theme="Creator",
            year_released=2013,
            parts_count=271,
            image_url="https://example.com/img.png",
        )

        items = get_items_needing_enrichment(conn, limit=10)
        set_numbers = [item["set_number"] for item in items]
        queued = queue_enrichment_batch(manager, set_numbers)

        assert queued == 0

    def test_sweep_deduplicates_against_pending(self, conn, manager):
        """Given item needing enrichment AND existing pending job.
        When sweep runs.
        Then no duplicate job queued."""
        from services.enrichment.auto import queue_enrichment_batch
        from services.enrichment.repository import get_items_needing_enrichment

        get_or_create_item(conn, "75192")
        record_price(conn, "75192", source="toysrus", price_cents=329900, currency="MYR")
        manager.create_job("enrichment", "75192")

        items = get_items_needing_enrichment(conn, limit=10)
        set_numbers = [item["set_number"] for item in items]
        queued = queue_enrichment_batch(manager, set_numbers)

        assert queued == 0
        assert len(manager.list_jobs()) == 1


class TestPostScrapeEnrichment:
    """Tests for auto-enrichment triggered after scraping."""

    def test_extracts_set_numbers_from_titles(self):
        """Given scraped items with LEGO set numbers in titles.
        When extracting set numbers.
        Then valid set numbers found."""
        from services.items.set_number import extract_set_number

        items = [
            {"title": "LEGO Star Wars 75192 Millennium Falcon (7541 Pcs)"},
            {"title": "LEGO 42151 Technic Bugatti Bolide"},
            {"title": "Random toy with no set number"},
            {"title": ""},
        ]

        set_numbers = []
        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            sn = extract_set_number(title)
            if sn:
                set_numbers.append(sn)

        assert "75192" in set_numbers
        assert "42151" in set_numbers
        assert len(set_numbers) == 2

    def test_queues_enrichment_for_extracted_sets(self, manager):
        """Given extracted set numbers from scrape.
        When batch queuing enrichment.
        Then jobs queued for each unique set."""
        from services.enrichment.auto import queue_enrichment_batch

        set_numbers = ["75192", "42151", "75192"]  # dupe
        queued = queue_enrichment_batch(manager, set_numbers)

        assert queued == 2
        jobs = manager.list_jobs()
        urls = {j.url for j in jobs}
        assert "75192" in urls
        assert "42151" in urls
