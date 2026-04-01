"""Feature registry for the ML pipeline.

Provides a central registry for all features with metadata.
Adding a feature: call register() at module scope in feature_extractors.py.
Removing a feature: call disable() or remove the register() call.
"""

import logging

from services.ml.types import FeatureMeta

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, FeatureMeta] = {}


def register(
    name: str,
    source_table: str,
    description: str,
    dtype: str = "float",
) -> None:
    """Register a feature in the global registry."""
    _REGISTRY[name] = FeatureMeta(
        name=name,
        source_table=source_table,
        description=description,
        dtype=dtype,
        is_enabled=True,
    )


def disable(name: str) -> None:
    """Disable a feature (excluded from training but kept in registry)."""
    if name in _REGISTRY:
        current = _REGISTRY[name]
        _REGISTRY[name] = FeatureMeta(
            name=current.name,
            source_table=current.source_table,
            description=current.description,
            dtype=current.dtype,
            is_enabled=False,
        )
    else:
        logger.warning("Cannot disable unknown feature: %s", name)


def enable(name: str) -> None:
    """Re-enable a previously disabled feature."""
    if name in _REGISTRY:
        current = _REGISTRY[name]
        _REGISTRY[name] = FeatureMeta(
            name=current.name,
            source_table=current.source_table,
            description=current.description,
            dtype=current.dtype,
            is_enabled=True,
        )
    else:
        logger.warning("Cannot enable unknown feature: %s", name)


def get_enabled() -> list[FeatureMeta]:
    """Return all enabled features."""
    return [f for f in _REGISTRY.values() if f.is_enabled]


def get_enabled_names() -> list[str]:
    """Return names of all enabled features."""
    return [f.name for f in _REGISTRY.values() if f.is_enabled]


def get_all() -> list[FeatureMeta]:
    """Return all registered features (including disabled)."""
    return list(_REGISTRY.values())


def get(name: str) -> FeatureMeta | None:
    """Return a single feature by name."""
    return _REGISTRY.get(name)


def clear() -> None:
    """Clear all registrations (for testing)."""
    _REGISTRY.clear()
