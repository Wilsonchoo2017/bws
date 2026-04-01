"""GWT tests for EnrichmentWorker -- proves it handles the enrichment data source."""

import asyncio
from unittest.mock import patch

from api.jobs import JobManager
from api.workers.enrichment import EnrichmentWorker


class TestEnrichmentWorkerIdentity:
    """Given an EnrichmentWorker, verify it identifies as the enrichment source."""

    def test_given_enrichment_worker_when_scraper_id_checked_then_matches_enrichment(self):
        """Given an EnrichmentWorker, when scraper_id checked, then it is 'enrichment'."""
        worker = EnrichmentWorker()
        assert worker.scraper_id == "enrichment"


class TestEnrichmentWorkerRun:
    """Given an enrichment job, verify the worker processes it correctly."""

    def test_given_enrichment_job_when_processed_then_returns_field_counts(self):
        """Given an enrichment job, when worker runs, then returns task counts in WorkResult."""
        worker = EnrichmentWorker()
        mgr = JobManager()
        job = mgr.create_job("enrichment", "75192")

        fake_result = {
            "set_number": "75192",
            "tasks_created": 3,
            "task_types": ["bricklink_metadata", "brickeconomy", "keepa"],
        }

        with patch(
            "api.workers.enrichment._create_scrape_tasks",
            return_value=fake_result,
        ):
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 3
        assert "75192" in result.log_summary

    def test_given_enrichment_job_when_item_not_found_then_returns_zero(self):
        """Given an enrichment job with no tasks created, when run, then returns 0."""
        worker = EnrichmentWorker()
        mgr = JobManager()
        job = mgr.create_job("enrichment", "99999")

        fake_result = {
            "set_number": "99999",
            "tasks_created": 0,
            "task_types": [],
        }

        with patch(
            "api.workers.enrichment._create_scrape_tasks",
            return_value=fake_result,
        ):
            result = asyncio.run(worker.run(job, mgr))

        assert result.items_found == 0
