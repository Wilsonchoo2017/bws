"""Scoring provider protocol and registry.

Defines a pluggable interface for enriching item signals with
predictions from different models. New models implement the
``ScoringProvider`` protocol and register via ``register_provider``.

The signals endpoint calls ``enrich_all`` to layer predictions from
all registered providers onto the signal dicts.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable


logger = logging.getLogger(__name__)


@runtime_checkable
class ScoringProvider(Protocol):
    """Interface for a scoring/prediction provider.

    Each provider returns a dict mapping set_number -> prediction dict.
    The prediction dict keys become fields on the signal response
    (prefixed with the provider's ``prefix``).
    """

    @property
    def name(self) -> str:
        """Human-readable name for logging."""
        ...

    @property
    def prefix(self) -> str:
        """Key prefix for fields added to signals (e.g. 'ml_')."""
        ...

    def score_all(self, conn: Any) -> dict[str, dict]:
        """Return {set_number: {field: value, ...}} for all scoreable sets.

        Must not raise -- return empty dict on failure.
        """
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_providers: list[ScoringProvider] = []


def register_provider(provider: ScoringProvider) -> None:
    """Register a scoring provider."""
    _providers.append(provider)
    logger.info("Registered scoring provider: %s", provider.name)


def get_providers() -> list[ScoringProvider]:
    """Return all registered providers."""
    return list(_providers)


def enrich_signals(
    signals: list[dict],
    conn: Any,
) -> list[dict]:
    """Enrich signal dicts with predictions from all registered providers.

    Each provider's output is merged into matching signal dicts by set_number.
    Provider failures are logged and skipped -- never breaks the signals response.
    """
    for provider in _providers:
        try:
            scores = provider.score_all(conn)
        except Exception:
            logger.warning(
                "Scoring provider %s failed, skipping",
                provider.name,
                exc_info=True,
            )
            continue

        if not scores:
            continue

        prefix = provider.prefix
        for sig in signals:
            sn = sig.get("set_number") or str(sig.get("item_id", "")).split("-")[0]
            pred = scores.get(sn)
            if pred:
                for key, val in pred.items():
                    sig[f"{prefix}{key}"] = val

    return signals
