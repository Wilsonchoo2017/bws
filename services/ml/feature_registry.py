"""Feature registry for the ML pipeline.

Provides a class-based registry for all features with metadata.
The module-level functions use a default singleton instance for
backward compatibility.

For testing, create a separate FeatureRegistry instance to avoid
global state pollution.
"""

import logging

from services.ml.types import FeatureMeta

logger = logging.getLogger(__name__)


class FeatureRegistry:
    """Registry for ML feature metadata.

    Stores FeatureMeta entries indexed by name with enable/disable support.
    """

    def __init__(self) -> None:
        self._registry: dict[str, FeatureMeta] = {}

    def register(
        self,
        name: str,
        source_table: str,
        description: str,
        dtype: str = "float",
    ) -> None:
        """Register a feature."""
        self._registry[name] = FeatureMeta(
            name=name,
            source_table=source_table,
            description=description,
            dtype=dtype,
            is_enabled=True,
        )

    def disable(self, name: str) -> None:
        """Disable a feature (excluded from training but kept in registry)."""
        if name in self._registry:
            current = self._registry[name]
            self._registry[name] = FeatureMeta(
                name=current.name,
                source_table=current.source_table,
                description=current.description,
                dtype=current.dtype,
                is_enabled=False,
            )
        else:
            logger.warning("Cannot disable unknown feature: %s", name)

    def enable(self, name: str) -> None:
        """Re-enable a previously disabled feature."""
        if name in self._registry:
            current = self._registry[name]
            self._registry[name] = FeatureMeta(
                name=current.name,
                source_table=current.source_table,
                description=current.description,
                dtype=current.dtype,
                is_enabled=True,
            )
        else:
            logger.warning("Cannot enable unknown feature: %s", name)

    def get_enabled(self) -> list[FeatureMeta]:
        """Return all enabled features."""
        return [f for f in self._registry.values() if f.is_enabled]

    def get_enabled_names(self) -> list[str]:
        """Return names of all enabled features."""
        return [f.name for f in self._registry.values() if f.is_enabled]

    def get_all(self) -> list[FeatureMeta]:
        """Return all registered features (including disabled)."""
        return list(self._registry.values())

    def get(self, name: str) -> FeatureMeta | None:
        """Return a single feature by name."""
        return self._registry.get(name)

    def clear(self) -> None:
        """Clear all registrations (for testing)."""
        self._registry.clear()


# ---------------------------------------------------------------------------
# Default singleton instance + module-level functions for backward compat
# ---------------------------------------------------------------------------

_default_registry = FeatureRegistry()


def register(
    name: str,
    source_table: str,
    description: str,
    dtype: str = "float",
) -> None:
    """Register a feature in the default global registry."""
    _default_registry.register(name, source_table, description, dtype)


def disable(name: str) -> None:
    """Disable a feature in the default global registry."""
    _default_registry.disable(name)


def enable(name: str) -> None:
    """Re-enable a feature in the default global registry."""
    _default_registry.enable(name)


def get_enabled() -> list[FeatureMeta]:
    """Return all enabled features from the default registry."""
    return _default_registry.get_enabled()


def get_enabled_names() -> list[str]:
    """Return names of all enabled features from the default registry."""
    return _default_registry.get_enabled_names()


def get_all() -> list[FeatureMeta]:
    """Return all registered features from the default registry."""
    return _default_registry.get_all()


def get(name: str) -> FeatureMeta | None:
    """Return a single feature by name from the default registry."""
    return _default_registry.get(name)


def clear() -> None:
    """Clear the default registry (for testing)."""
    _default_registry.clear()
