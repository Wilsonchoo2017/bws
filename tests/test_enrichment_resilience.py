"""GROUP 6: Resilience tests for metadata enrichment."""

from datetime import datetime, timedelta, timezone

import pytest

from services.enrichment.circuit_breaker import (
    CircuitBreakerState,
    SourceState,
    is_available,
    record_failure,
    record_success,
)
from services.enrichment.orchestrator import determine_sources_needed, enrich
from services.enrichment.source_adapter import make_failed_result
from services.enrichment.types import (
    FieldStatus,
    MetadataField,
    SourceId,
    SourceResult,
)


class TestCircuitBreaker:
    """Tests for circuit breaker state transitions."""

    def test_initial_state_is_closed(self):
        """Given fresh circuit breaker. Then all sources available."""
        cb = CircuitBreakerState()
        assert is_available(cb, SourceId.BRICKLINK, cooldown_seconds=1800)
        assert is_available(cb, SourceId.BRICKECONOMY, cooldown_seconds=1800)

    def test_single_failure_does_not_trip(self):
        """Given 1 failure (threshold=5). Then source still available."""
        cb = CircuitBreakerState()
        cb = record_failure(cb, SourceId.BRICKLINK, threshold=5)
        assert is_available(cb, SourceId.BRICKLINK, cooldown_seconds=1800)
        assert cb.get_state(SourceId.BRICKLINK).consecutive_failures == 1

    def test_threshold_trips_breaker(self):
        """Given 5 consecutive failures (threshold=5). Then breaker trips."""
        cb = CircuitBreakerState()
        for _ in range(5):
            cb = record_failure(cb, SourceId.BRICKECONOMY, threshold=5)

        state = cb.get_state(SourceId.BRICKECONOMY)
        assert state.is_open
        assert state.consecutive_failures == 5
        assert not is_available(cb, SourceId.BRICKECONOMY, cooldown_seconds=1800)

    def test_success_resets_failures(self):
        """Given 4 failures then 1 success. Then counter resets."""
        cb = CircuitBreakerState()
        for _ in range(4):
            cb = record_failure(cb, SourceId.BRICKLINK, threshold=5)
        cb = record_success(cb, SourceId.BRICKLINK)

        state = cb.get_state(SourceId.BRICKLINK)
        assert state.consecutive_failures == 0
        assert not state.is_open

    def test_cooldown_expires_allows_retry(self):
        """Given tripped breaker with expired cooldown. Then source available."""
        old_time = datetime.now(tz=timezone.utc) - timedelta(seconds=3600)
        cb = CircuitBreakerState(
            states={
                SourceId.BRICKECONOMY: SourceState(
                    consecutive_failures=5,
                    last_failure_at=old_time,
                    is_open=True,
                )
            }
        )
        # Cooldown is 1800s, 3600s have passed
        assert is_available(cb, SourceId.BRICKECONOMY, cooldown_seconds=1800)

    def test_cooldown_not_expired_blocks(self):
        """Given tripped breaker with recent failure. Then source blocked."""
        recent_time = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
        cb = CircuitBreakerState(
            states={
                SourceId.BRICKECONOMY: SourceState(
                    consecutive_failures=5,
                    last_failure_at=recent_time,
                    is_open=True,
                )
            }
        )
        assert not is_available(cb, SourceId.BRICKECONOMY, cooldown_seconds=1800)

    def test_other_sources_unaffected(self):
        """Given BrickEconomy tripped. Then Bricklink still available."""
        cb = CircuitBreakerState()
        for _ in range(5):
            cb = record_failure(cb, SourceId.BRICKECONOMY, threshold=5)

        assert not is_available(cb, SourceId.BRICKECONOMY, cooldown_seconds=1800)
        assert is_available(cb, SourceId.BRICKLINK, cooldown_seconds=1800)


class TestResilienceIntegration:
    """GROUP 6: Resilience integration tests."""

    def test_6_2_circuit_breaker_skips_source(self, make_item):
        """Given Bricklink and BrickEconomy circuit breakers open.
        When enrichment needs weight (Bricklink-only).
        Then Bricklink skipped, field marked SKIPPED."""
        item = make_item()

        # Pre-trip both circuit breakers
        cb = CircuitBreakerState()
        for _ in range(5):
            cb = record_failure(cb, SourceId.BRICKLINK, threshold=5)
            cb = record_failure(cb, SourceId.BRICKECONOMY, threshold=5)

        bricklink_called = False

        def bricklink_fetcher(set_number: str) -> SourceResult:
            nonlocal bricklink_called
            bricklink_called = True
            return SourceResult(
                source=SourceId.BRICKLINK, success=True, fields={}
            )

        result, _ = enrich(
            "10305",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            cb,
            fields=(MetadataField.WEIGHT,),
        )

        assert not bricklink_called
        weight_r = next(
            r for r in result.field_results if r.field == MetadataField.WEIGHT
        )
        assert weight_r.status == FieldStatus.SKIPPED

    def test_6_2_circuit_breaker_determine_sources_excludes_tripped(self):
        """Given Bricklink tripped.
        Then determine_sources_needed excludes it."""
        cb = CircuitBreakerState()
        for _ in range(5):
            cb = record_failure(cb, SourceId.BRICKLINK, threshold=5)

        sources = determine_sources_needed((MetadataField.WEIGHT,), cb)
        assert SourceId.BRICKLINK not in sources

    def test_6_3_enrichment_updates_cb_on_failure(self, make_item):
        """Given Bricklink fails during enrichment.
        Then circuit breaker state updated with failure."""
        item = make_item()

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return make_failed_result(SourceId.BRICKLINK, "HTTP 429: Too Many Requests")

        _, new_cb = enrich(
            "75252",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            CircuitBreakerState(),
            fields=(MetadataField.WEIGHT,),
        )

        state = new_cb.get_state(SourceId.BRICKLINK)
        assert state.consecutive_failures == 1

    def test_6_3_enrichment_updates_cb_on_success(self, make_item):
        """Given Bricklink succeeds during enrichment.
        Then circuit breaker resets."""
        item = make_item()

        # Start with some failures
        cb = CircuitBreakerState()
        for _ in range(3):
            cb = record_failure(cb, SourceId.BRICKLINK, threshold=5)

        def bricklink_fetcher(set_number: str) -> SourceResult:
            return SourceResult(
                source=SourceId.BRICKLINK,
                success=True,
                fields={MetadataField.WEIGHT: "1.5 kg"},
            )

        _, new_cb = enrich(
            "75252",
            item,
            {SourceId.BRICKLINK: bricklink_fetcher},
            cb,
            fields=(MetadataField.WEIGHT,),
        )

        state = new_cb.get_state(SourceId.BRICKLINK)
        assert state.consecutive_failures == 0

    def test_6_5_all_sources_unavailable(self, make_item):
        """Given all relevant sources circuit-broken.
        Then fields marked SKIPPED, no fetchers called."""
        item = make_item()

        cb = CircuitBreakerState()
        for _ in range(5):
            cb = record_failure(cb, SourceId.BRICKLINK, threshold=5)
            cb = record_failure(cb, SourceId.BRICKECONOMY, threshold=5)

        call_count = 0

        def any_fetcher(set_number: str) -> SourceResult:
            nonlocal call_count
            call_count += 1
            return SourceResult(source=SourceId.BRICKLINK, success=True, fields={})

        result, _ = enrich(
            "75192",
            item,
            {SourceId.BRICKLINK: any_fetcher},
            cb,
            fields=(MetadataField.YEAR_RELEASED,),
        )

        assert call_count == 0
        year_r = next(r for r in result.field_results if r.field == MetadataField.YEAR_RELEASED)
        assert year_r.status == FieldStatus.SKIPPED
