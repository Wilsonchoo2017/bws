"""Runtime-adjustable operational settings with JSON persistence.

Settings are loaded from ``~/.bws/runtime_settings.json`` on startup
and written back on every update.  Each setting category can be updated
independently via ``update_section()``.

Runtime changes propagate to the actual rate limiters, executor configs,
and scheduler intervals so that the effect is immediate without restart.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("bws.runtime_settings")

_SETTINGS_FILE = Path.home() / ".bws" / "runtime_settings.json"


# ---------------------------------------------------------------------------
# Setting schemas (one dataclass per section)
# ---------------------------------------------------------------------------


@dataclass
class SourceRateLimit:
    min_delay_ms: int
    max_delay_ms: int
    max_requests_per_hour: int


@dataclass
class CooldownSettings:
    base_cooldown_s: int = 3600
    forbidden_cooldown_s: int = 14400
    max_cooldown_s: int = 28800
    max_continuous_scrape_s: int = 10800
    rest_period_s: int = 1800


@dataclass
class WorkerSettings:
    concurrency: int
    timeout_s: int


@dataclass
class SchedulerSettings:
    interval_minutes: int
    batch_size: int


@dataclass
class DispatcherSettings:
    poll_interval_s: int = 3
    checkpoint_interval_s: int = 30


# ---------------------------------------------------------------------------
# Defaults -- these mirror the hardcoded values across the codebase
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "rate_limits": {
        "bricklink": {"min_delay_ms": 10_000, "max_delay_ms": 25_000, "max_requests_per_hour": 1_500},
        "brickeconomy": {"min_delay_ms": 8_000, "max_delay_ms": 20_000, "max_requests_per_hour": 120},
        "keepa": {"min_delay_ms": 5_000, "max_delay_ms": 15_000, "max_requests_per_hour": 200},
    },
    "cooldowns": {
        "base_cooldown_s": 3600,
        "forbidden_cooldown_s": 14400,
        "max_cooldown_s": 28800,
        "max_continuous_scrape_s": 10800,
        "rest_period_s": 1800,
    },
    "workers": {
        "bricklink_metadata": {"concurrency": 2, "timeout_s": 300},
        "brickeconomy": {"concurrency": 5, "timeout_s": 300},
        "keepa": {"concurrency": 5, "timeout_s": 300},
        "minifigures": {"concurrency": 1, "timeout_s": 600},
        "google_trends": {"concurrency": 1, "timeout_s": 180},
        "google_trends_theme": {"concurrency": 1, "timeout_s": 180},
    },
    "schedulers": {
        "enrichment": {"interval_minutes": 30, "batch_size": 10},
        "rescrape": {"interval_minutes": 60, "batch_size": 30},
        "saturation": {"interval_minutes": 360, "batch_size": 50},
        "keepa": {"interval_minutes": 60, "batch_size": 1000},
        "images": {"interval_minutes": 5, "batch_size": 50},
    },
    "dispatcher": {
        "poll_interval_s": 3,
        "checkpoint_interval_s": 30,
    },
    "paused_workers": [],
    "suppliers": [],
    "platforms": [],
    "listing": {
        "shopee": {
            "max_photos": 9,
            "category": "",
        },
        "facebook": {
            "max_photos": 10,
        },
    },
    "cart": {
        "min_liquidity_score": 50,
        "deal_threshold_pct": 5,
        "min_confidence": "high",
        "max_avoid_probability": 0.5,
        "min_growth_pct": 8,
    },
    "forward_return": {
        "min_return": 0.20,
        "target_return": 0.50,
        "default_horizon_years": 2.0,
        "retired_horizon_years": 1.0,
        "post_retirement_bonus_years": 1.5,
        "min_time_years": 0.25,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_copy(obj: Any) -> Any:
    """Return a deep copy via JSON round-trip (works for JSON-safe dicts)."""
    return json.loads(json.dumps(obj))


def _merge_defaults(defaults: dict, overrides: dict) -> dict:
    """Recursively merge overrides into defaults, keeping default keys."""
    result = _deep_copy(defaults)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_defaults(result[key], value)
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Singleton settings store
# ---------------------------------------------------------------------------


class RuntimeSettings:
    """In-memory settings store backed by a JSON file."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = _deep_copy(_DEFAULTS)

    # -- persistence --------------------------------------------------------

    def load(self) -> None:
        """Load settings from disk, falling back to defaults for missing keys."""
        if not _SETTINGS_FILE.exists():
            logger.info("No runtime settings file; using defaults")
            return
        try:
            saved = json.loads(_SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read %s; using defaults", _SETTINGS_FILE)
            return
        self._data = _merge_defaults(_DEFAULTS, saved)
        logger.info("Loaded runtime settings from %s", _SETTINGS_FILE)
        # Apply all sections to live objects
        for section, values in self._data.items():
            try:
                _apply_runtime(section, values)
            except Exception:
                logger.warning("Failed to apply %s settings on load", section, exc_info=True)

    def save(self) -> None:
        """Persist current settings to disk."""
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(self._data, indent=2))

    # -- access -------------------------------------------------------------

    def get_all(self) -> dict[str, Any]:
        """Return a deep copy of all settings."""
        return _deep_copy(self._data)

    def get_section(self, section: str) -> dict[str, Any]:
        return _deep_copy(self._data.get(section, {}))

    def update_section(self, section: str, values: dict[str, Any]) -> None:
        """Update a settings section and propagate to runtime objects."""
        if section not in self._data:
            raise KeyError(f"Unknown settings section: {section}")
        if isinstance(self._data[section], dict):
            self._data[section] = _merge_defaults(self._data[section], values)
        else:
            self._data[section] = values
        self.save()
        _apply_runtime(section, self._data[section])

    def get_defaults(self) -> dict[str, Any]:
        """Return factory defaults for comparison."""
        return _deep_copy(_DEFAULTS)


# Module-level singleton
runtime_settings = RuntimeSettings()


# ---------------------------------------------------------------------------
# Runtime propagation -- push changed values into live objects
# ---------------------------------------------------------------------------


def _apply_runtime(section: str, values: dict[str, Any]) -> None:
    """Push settings into live runtime objects so changes take effect immediately."""
    if section == "rate_limits":
        _apply_rate_limits(values)
    elif section == "cooldowns":
        _apply_cooldowns(values)
    elif section == "workers":
        _apply_workers(values)
    elif section == "schedulers":
        _apply_schedulers(values)
    elif section == "dispatcher":
        _apply_dispatcher(values)
    elif section == "paused_workers":
        _apply_paused_workers(values)
    elif section == "listing":
        pass  # static config, no live propagation needed
    elif section == "cart":
        pass  # static config, no live propagation needed
    elif section == "suppliers":
        pass  # static config, no live propagation needed
    elif section == "platforms":
        pass  # static config, no live propagation needed


def _apply_rate_limits(values: dict[str, Any]) -> None:
    """Update live rate limiters with new max_requests_per_hour."""
    from config.settings import _domain_registry

    domain_map = {
        "bricklink": "bricklink.com",
        "brickeconomy": "brickeconomy.com",
        "keepa": "keepa.com",
    }
    for source, domain in domain_map.items():
        if source not in values:
            continue
        limiter = _domain_registry.get(domain)
        if limiter is not None:
            new_max = values[source].get("max_requests_per_hour")
            if new_max is not None:
                limiter._max_per_hour = new_max
    logger.info("Applied rate limit settings")


def _apply_cooldowns(values: dict[str, Any]) -> None:
    """Update HourlyRateLimiter class-level cooldown constants."""
    from config.settings import HourlyRateLimiter

    mapping = {
        "base_cooldown_s": "BASE_COOLDOWN_SECONDS",
        "forbidden_cooldown_s": "FORBIDDEN_COOLDOWN_SECONDS",
        "max_cooldown_s": "MAX_COOLDOWN_SECONDS",
        "max_continuous_scrape_s": "MAX_CONTINUOUS_SCRAPE_SECONDS",
        "rest_period_s": "REST_PERIOD_SECONDS",
    }
    for key, attr in mapping.items():
        if key in values:
            setattr(HourlyRateLimiter, attr, float(values[key]))
    logger.info("Applied cooldown settings")


def _apply_workers(values: dict[str, Any]) -> None:
    """Update executor concurrency and timeout in the registry."""
    from services.scrape_queue.registry import REGISTRY
    from services.scrape_queue.models import TaskType

    task_type_map = {
        "bricklink_metadata": TaskType.BRICKLINK_METADATA,
        "brickeconomy": TaskType.BRICKECONOMY,
        "keepa": TaskType.KEEPA,
        "minifigures": TaskType.MINIFIGURES,
        "google_trends": TaskType.GOOGLE_TRENDS,
        "google_trends_theme": TaskType.GOOGLE_TRENDS_THEME,
    }
    from dataclasses import replace
    for key, tt in task_type_map.items():
        if key not in values or tt not in REGISTRY:
            continue
        cfg = REGISTRY[tt]
        new_concurrency = values[key].get("concurrency")
        new_timeout = values[key].get("timeout_s")
        updates: dict[str, Any] = {}
        if new_concurrency is not None:
            updates["concurrency"] = new_concurrency
        if new_timeout is not None:
            updates["timeout_seconds"] = new_timeout
        if updates:
            REGISTRY[tt] = replace(cfg, **updates)
    logger.info("Applied worker settings")


def _apply_schedulers(values: dict[str, Any]) -> None:
    """Update scheduler module-level constants."""
    if "enrichment" in values:
        import services.enrichment.scheduler as m
        m.DEFAULT_INTERVAL_MINUTES = values["enrichment"].get("interval_minutes", m.DEFAULT_INTERVAL_MINUTES)
        m.DEFAULT_BATCH_SIZE = values["enrichment"].get("batch_size", m.DEFAULT_BATCH_SIZE)

    if "rescrape" in values:
        import services.enrichment.scheduler as m
        m.RESCRAPE_INTERVAL_MINUTES = values["rescrape"].get("interval_minutes", m.RESCRAPE_INTERVAL_MINUTES)

    if "saturation" in values:
        import services.shopee.saturation_scheduler as m
        m.DEFAULT_INTERVAL_MINUTES = values["saturation"].get("interval_minutes", m.DEFAULT_INTERVAL_MINUTES)
        m.DEFAULT_BATCH_SIZE = values["saturation"].get("batch_size", m.DEFAULT_BATCH_SIZE)

    if "keepa" in values:
        import services.keepa.scheduler as m
        m.DEFAULT_INTERVAL_MINUTES = values["keepa"].get("interval_minutes", m.DEFAULT_INTERVAL_MINUTES)
        m.DEFAULT_BATCH_SIZE = values["keepa"].get("batch_size", m.DEFAULT_BATCH_SIZE)

    if "images" in values:
        import services.images.sweep as m
        m._SWEEP_INTERVAL_S = values["images"].get("interval_minutes", 5) * 60
        m._BATCH_SIZE = values["images"].get("batch_size", m._BATCH_SIZE)

    logger.info("Applied scheduler settings")


def _apply_dispatcher(values: dict[str, Any]) -> None:
    """Update dispatcher poll/checkpoint intervals."""
    import services.scrape_queue.dispatcher as m

    if "poll_interval_s" in values:
        m._POLL_INTERVAL = values["poll_interval_s"]
    if "checkpoint_interval_s" in values:
        m._CHECKPOINT_INTERVAL = values["checkpoint_interval_s"]
    logger.info("Applied dispatcher settings")


def _apply_paused_workers(values: Any) -> None:
    """Update the dispatcher's paused worker set."""
    import services.scrape_queue.dispatcher as m

    paused = set(values) if isinstance(values, list) else set()
    m._paused_workers = paused
    logger.info("Applied paused workers: %s", paused or "(none)")
