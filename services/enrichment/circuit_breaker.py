"""Circuit breaker for metadata sources.

Tracks consecutive failures per source and trips after threshold.
Immutable state transitions -- each call returns a new state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.enrichment.types import SourceId


@dataclass(frozen=True)
class SourceState:
    """Immutable state for a single source's circuit breaker."""

    consecutive_failures: int = 0
    last_failure_at: datetime | None = None
    is_open: bool = False


@dataclass(frozen=True)
class CircuitBreakerState:
    """Immutable state for all source circuit breakers."""

    states: dict[SourceId, SourceState] = field(default_factory=dict)

    def get_state(self, source_id: SourceId) -> SourceState:
        return self.states.get(source_id, SourceState())


def record_failure(
    state: CircuitBreakerState,
    source_id: SourceId,
    threshold: int,
) -> CircuitBreakerState:
    """Record a failure and return new state. Trips breaker if threshold reached."""
    current = state.get_state(source_id)
    new_failures = current.consecutive_failures + 1
    now = datetime.now(tz=timezone.utc)

    new_source_state = SourceState(
        consecutive_failures=new_failures,
        last_failure_at=now,
        is_open=new_failures >= threshold,
    )

    return CircuitBreakerState(
        states={**state.states, source_id: new_source_state},
    )


def record_success(
    state: CircuitBreakerState,
    source_id: SourceId,
) -> CircuitBreakerState:
    """Record a success and return new state. Resets failure count."""
    return CircuitBreakerState(
        states={**state.states, source_id: SourceState()},
    )


def is_available(
    state: CircuitBreakerState,
    source_id: SourceId,
    cooldown_seconds: int,
) -> bool:
    """Check if a source is available (breaker closed or cooldown expired)."""
    source_state = state.get_state(source_id)

    if not source_state.is_open:
        return True

    if source_state.last_failure_at is None:
        return True

    now = datetime.now(tz=timezone.utc)
    elapsed = (now - source_state.last_failure_at).total_seconds()
    return elapsed >= cooldown_seconds
