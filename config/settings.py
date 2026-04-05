"""BWS configuration settings.

Rate limiting, user agents, and other scraper configuration.
"""


import asyncio
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# Database path (isolated from MoonBridge)
BWS_DB_PATH = Path.home() / ".bws" / "bws.duckdb"

# PostgreSQL configuration
POSTGRES_URL = os.environ.get(
    "BWS_POSTGRES_URL",
    "postgresql+psycopg2://bws:bws@localhost:5432/bws",
)
PG_ENABLED = os.environ.get("BWS_PG_ENABLED", "false").lower() == "true"

# Local image storage
BWS_IMAGES_PATH = Path.home() / ".bws" / "images"
BWS_IMAGES_SETS_PATH = BWS_IMAGES_PATH / "sets"
BWS_IMAGES_MINIFIGS_PATH = BWS_IMAGES_PATH / "minifigs"
BWS_IMAGES_PARTS_PATH = BWS_IMAGES_PATH / "parts"


@dataclass(frozen=True)
class RateLimitSettings:
    """Rate limiting configuration."""

    min_delay_ms: int = 10_000  # 10 seconds
    max_delay_ms: int = 25_000  # 25 seconds
    max_requests_per_hour: int = 1_500


@dataclass(frozen=True)
class RetrySettings:
    """Retry and backoff configuration."""

    max_retries: int = 3
    initial_backoff_ms: int = 30_000  # 30 seconds
    max_backoff_ms: int = 300_000  # 5 minutes
    backoff_multiplier: float = 2.0


# Default configurations
RATE_LIMIT_CONFIG = RateLimitSettings()
RETRY_CONFIG = RetrySettings()


# User agent pool for rotation - Mix of browsers and devices
USER_AGENTS: tuple[str, ...] = (
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:119.0) Gecko/20100101 Firefox/119.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    # Safari on iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
)

# Accept-Language headers pool for rotation
ACCEPT_LANGUAGES: tuple[str, ...] = (
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en,en-US;q=0.9",
)


def get_random_user_agent() -> str:
    """Get a random user agent from the pool."""
    return secrets.choice(USER_AGENTS)


def get_random_accept_language() -> str:
    """Get a random Accept-Language header from the pool."""
    return secrets.choice(ACCEPT_LANGUAGES)


def get_random_delay(
    min_ms: int | None = None,
    max_ms: int | None = None,
) -> float:
    """Get a random delay in seconds.

    Args:
        min_ms: Minimum delay in milliseconds (default: RATE_LIMIT_CONFIG.min_delay_ms)
        max_ms: Maximum delay in milliseconds (default: RATE_LIMIT_CONFIG.max_delay_ms)

    Returns:
        Random delay in seconds
    """
    min_delay = min_ms if min_ms is not None else RATE_LIMIT_CONFIG.min_delay_ms
    max_delay = max_ms if max_ms is not None else RATE_LIMIT_CONFIG.max_delay_ms
    # secrets.randbelow(n) returns [0, n), so we add min_delay and use range size
    return (min_delay + secrets.randbelow(max_delay - min_delay + 1)) / 1000.0


@dataclass(frozen=True)
class ShopeeSettings:
    """Shopee browser automation configuration."""

    base_url: str = "https://shopee.com.my"
    headless: bool = False
    timeout_ms: int = 30_000
    user_data_dir: str = str(Path.home() / ".bws" / "shopee-profile")
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "en-MY"
    timezone_id: str = "Asia/Kuala_Lumpur"
    min_action_delay_ms: int = 800
    max_action_delay_ms: int = 2_500


SHOPEE_CONFIG = ShopeeSettings()


@dataclass(frozen=True)
class SaturationSettings:
    """Shopee saturation checker configuration."""

    min_search_delay_ms: int = 30_000    # 30s between searches
    max_search_delay_ms: int = 90_000    # 90s max
    max_searches_per_session: int = 12   # close browser after this many
    session_cooldown_min_ms: int = 60_000   # 60s min between sessions
    session_cooldown_max_ms: int = 120_000  # 120s max between sessions
    stale_threshold_days: int = 7        # skip items checked within 7 days
    circuit_breaker_threshold: int = 5   # trip after 5 consecutive failures
    circuit_breaker_cooldown_s: int = 1800  # 30 minute cooldown


SATURATION_CONFIG = SaturationSettings()


@dataclass(frozen=True)
class CarousellSettings:
    """Carousell browser automation configuration."""

    base_url: str = "https://www.carousell.com.my"
    headless: bool = False
    timeout_ms: int = 30_000
    user_data_dir: str = str(Path.home() / ".bws" / "carousell-profile")
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "en-MY"
    timezone_id: str = "Asia/Kuala_Lumpur"
    captcha_timeout_s: int = 120  # seconds to wait for human captcha solve


CAROUSELL_CONFIG = CarousellSettings()


@dataclass(frozen=True)
class KeepaSettings:
    """Keepa browser automation configuration."""

    base_url: str = "https://keepa.com"
    headless: bool = False  # visible browser needed for captcha
    timeout_ms: int = 30_000
    user_data_dir: str = str(Path.home() / ".bws" / "keepa-profile")
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "en-US"
    captcha_timeout_s: int = 120
    min_delay_ms: int = 5_000
    max_delay_ms: int = 15_000
    max_requests_per_hour: int = 30  # conservative


KEEPA_CONFIG = KeepaSettings()


def calculate_backoff(attempt: int) -> float:
    """Calculate exponential backoff delay in seconds.

    Args:
        attempt: Attempt number (1-based)

    Returns:
        Backoff delay in seconds
    """
    delay_ms = RETRY_CONFIG.initial_backoff_ms * (RETRY_CONFIG.backoff_multiplier ** (attempt - 1))
    return min(delay_ms, RETRY_CONFIG.max_backoff_ms) / 1000.0


class HourlyRateLimiter:
    """Sliding-window rate limiter with escalating circuit breaker.

    Tracks request timestamps and enforces max requests per hour.
    Cooldowns escalate on consecutive trips: 1h -> 2h -> 4h -> 8h (max).
    A 403 Forbidden triggers a longer initial cooldown (4h) that also escalates.
    Successful requests (via ``record_success``) reset the escalation level.

    Enforces a mandatory rest period after sustained scraping to avoid
    triggering bot detection from continuous overnight activity.
    """

    BASE_COOLDOWN_SECONDS = 3600.0       # 1 hour base for 429
    FORBIDDEN_COOLDOWN_SECONDS = 14400.0  # 4 hours base for 403
    MAX_COOLDOWN_SECONDS = 28800.0       # 8 hours cap

    # Rest period: after this many seconds of continuous scraping, pause.
    MAX_CONTINUOUS_SCRAPE_SECONDS = 3 * 3600.0  # 3 hours
    REST_PERIOD_SECONDS = 1800.0                # 30 min rest

    def __init__(self, max_per_hour: int, source_name: str = "BrickLink") -> None:
        self._max_per_hour = max_per_hour
        self._source_name = source_name
        self._logger = logging.getLogger(f"bws.ratelimit.{source_name.lower()}")
        self._timestamps: list[float] = []
        self._lock: asyncio.Lock | None = None
        self._blocked_until: float = 0.0
        self._escalation_level: int = 0
        self._consecutive_failures: int = 0
        self._scraping_since: float = 0.0  # monotonic time when continuous scraping began
        self._was_blocked: bool = False  # track recovery

    def _get_lock(self) -> asyncio.Lock:
        """Return a lock bound to the current event loop, recreating if needed."""
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock._loop is not loop:  # type: ignore[attr-defined]
            self._lock = asyncio.Lock()
        return self._lock

    def _prune(self, now: float) -> None:
        """Remove timestamps older than 1 hour."""
        cutoff = now - 3600.0
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.pop(0)

    def _escalated_cooldown(self, base: float) -> float:
        """Calculate cooldown with exponential escalation."""
        cooldown = base * (2 ** self._escalation_level)
        return min(cooldown, self.MAX_COOLDOWN_SECONDS)

    def trip_quota_exceeded(self) -> None:
        """Block requests with escalating cooldown (429 rate limit)."""
        from services.notifications.scraper_alerts import alert_rate_limited

        cooldown = self._escalated_cooldown(self.BASE_COOLDOWN_SECONDS)
        self._blocked_until = time.monotonic() + cooldown
        self._escalation_level += 1
        self._consecutive_failures += 1
        self._was_blocked = True
        self._scraping_since = 0.0
        self._logger.warning(
            "Quota exceeded (level %d) — pausing %s requests for %.0f min",
            self._escalation_level, self._source_name, cooldown / 60,
        )
        alert_rate_limited(self._source_name, cooldown / 60, self._escalation_level)

    def trip_forbidden(self) -> None:
        """Block requests with long cooldown (403 Forbidden = IP ban)."""
        from services.notifications.scraper_alerts import alert_forbidden

        cooldown = self._escalated_cooldown(self.FORBIDDEN_COOLDOWN_SECONDS)
        self._blocked_until = time.monotonic() + cooldown
        self._escalation_level += 1
        self._consecutive_failures += 1
        self._was_blocked = True
        self._scraping_since = 0.0
        self._logger.warning(
            "403 Forbidden / IP banned (level %d) — pausing %s requests for %.0f min",
            self._escalation_level, self._source_name, cooldown / 60,
        )
        alert_forbidden(self._source_name, cooldown / 60, self._escalation_level)

    def trip_silent_ban(self) -> None:
        """Block requests when consecutive 0-field responses suggest a silent ban."""
        from services.notifications.scraper_alerts import alert_silent_ban

        cooldown = self._escalated_cooldown(self.FORBIDDEN_COOLDOWN_SECONDS)
        self._blocked_until = time.monotonic() + cooldown
        self._escalation_level += 1
        self._consecutive_failures += 1
        self._was_blocked = True
        self._scraping_since = 0.0
        self._logger.warning(
            "Silent ban detected (consecutive 0-field responses, level %d) "
            "— pausing %s requests for %.0f min",
            self._escalation_level, self._source_name, cooldown / 60,
        )
        alert_silent_ban(self._source_name, self._consecutive_failures, cooldown / 60)

    def record_success(self) -> None:
        """Reset escalation after a successful scrape."""
        from services.notifications.scraper_alerts import alert_recovered

        if self._was_blocked:
            alert_recovered(self._source_name)
            self._was_blocked = False
        self._escalation_level = 0
        self._consecutive_failures = 0

    def is_blocked(self) -> bool:
        """Check if the limiter is currently in cooldown."""
        return time.monotonic() < self._blocked_until

    def cooldown_remaining(self) -> float:
        """Seconds remaining in cooldown, or 0.0 if not blocked."""
        return max(0.0, self._blocked_until - time.monotonic())

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive cooldown trips without a success."""
        return self._consecutive_failures

    def to_snapshot(self) -> dict:
        """Export cooldown state as a JSON-serialisable dict using wall-clock time."""
        remaining = self.cooldown_remaining()
        return {
            "blocked_until_wallclock": time.time() + remaining if remaining > 0 else 0.0,
            "escalation_level": self._escalation_level,
            "consecutive_failures": self._consecutive_failures,
            "was_blocked": self._was_blocked,
        }

    def restore_snapshot(self, snap: dict) -> None:
        """Restore cooldown state from a previously saved snapshot."""
        blocked_wall = snap.get("blocked_until_wallclock", 0.0)
        remaining = blocked_wall - time.time()
        if remaining > 0:
            self._blocked_until = time.monotonic() + remaining
            logger = logging.getLogger("bws.cooldown")
            logger.info(
                "Restored %s cooldown: %.0f min remaining",
                self._source_name, remaining / 60,
            )
        else:
            self._blocked_until = 0.0
        self._escalation_level = snap.get("escalation_level", 0)
        self._consecutive_failures = snap.get("consecutive_failures", 0)
        self._was_blocked = snap.get("was_blocked", False)

    def _check_rest_period(self, now: float) -> float:
        """Enforce mandatory rest after sustained continuous scraping.

        Returns seconds to rest, or 0.0 if no rest needed.
        """
        from services.notifications.scraper_alerts import alert_rest_period

        if self._scraping_since == 0.0:
            self._scraping_since = now
            return 0.0

        elapsed = now - self._scraping_since
        if elapsed >= self.MAX_CONTINUOUS_SCRAPE_SECONDS:
            self._scraping_since = 0.0  # will reset on next acquire
            self._logger.warning(
                "Continuous scraping for %.0f min — resting for %.0f min",
                elapsed / 60, self.REST_PERIOD_SECONDS / 60,
            )
            alert_rest_period(
                self._source_name,
                self.REST_PERIOD_SECONDS / 60,
                elapsed / 3600,
            )
            return self.REST_PERIOD_SECONDS
        return 0.0

    async def acquire(self) -> None:
        """Wait until a request slot is available, then record it."""
        async with self._get_lock():
            now = time.monotonic()

            # Wait out quota cooldown if active
            if now < self._blocked_until:
                wait = self._blocked_until - now
                self._logger.info(
                    "%s cooldown active: sleeping %.0f min", self._source_name, wait / 60,
                )
                await asyncio.sleep(wait)
                now = time.monotonic()
                self._logger.info("%s cooldown finished, resuming", self._source_name)

            # Enforce mandatory rest after sustained scraping
            rest = self._check_rest_period(now)
            if rest > 0:
                self._logger.info(
                    "%s mandatory rest: sleeping %.0f min", self._source_name, rest / 60,
                )
                await asyncio.sleep(rest)
                now = time.monotonic()
                self._logger.info("%s rest finished, resuming", self._source_name)

            self._prune(now)

            if len(self._timestamps) >= self._max_per_hour:
                wait = self._timestamps[0] - (now - 3600.0)
                if wait > 0:
                    self._logger.info(
                        "%s hourly quota full (%d/%d): sleeping %.0f s",
                        self._source_name, len(self._timestamps),
                        self._max_per_hour, wait,
                    )
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                    self._prune(now)

            self._timestamps.append(now)


# ---------------------------------------------------------------------------
# Domain rate limiter registry
#
# RULE: all requests to the same domain MUST share a single rate limiter.
# Register once via ``register_domain_limiter``, then look up with
# ``get_domain_limiter``.  Any new scraper/downloader hitting a registered
# domain gets the same limiter automatically -- no duplicate instances.
# ---------------------------------------------------------------------------

_domain_registry: dict[str, HourlyRateLimiter] = {}


def register_domain_limiter(
    domain: str,
    max_per_hour: int,
    source_name: str,
) -> HourlyRateLimiter:
    """Register (or retrieve) the rate limiter for a domain.

    If the domain already has a limiter, returns the existing one.
    This enforces one-limiter-per-domain across the whole codebase.
    """
    if domain in _domain_registry:
        return _domain_registry[domain]
    limiter = HourlyRateLimiter(max_per_hour, source_name=source_name)
    _domain_registry[domain] = limiter
    return limiter


def get_domain_limiter(domain: str) -> HourlyRateLimiter | None:
    """Look up the rate limiter for a domain. Returns None if unregistered."""
    return _domain_registry.get(domain)


# --- BrickLink (www.bricklink.com + img.bricklink.com = same domain) ---
BRICKLINK_RATE_LIMITER = register_domain_limiter(
    "bricklink.com",
    RATE_LIMIT_CONFIG.max_requests_per_hour,
    source_name="BrickLink",
)


@dataclass(frozen=True)
class BrickeconomySettings:
    """BrickEconomy browser automation configuration."""

    base_url: str = "https://www.brickeconomy.com"
    headless: bool = True
    timeout_ms: int = 30_000
    locale: str = "en-US"
    captcha_timeout_s: int = 120
    min_delay_ms: int = 8_000
    max_delay_ms: int = 20_000
    max_requests_per_hour: int = 60


BRICKECONOMY_CONFIG = BrickeconomySettings()

# --- BrickEconomy (brickeconomy.com) ---
BRICKECONOMY_RATE_LIMITER = register_domain_limiter(
    "brickeconomy.com",
    BRICKECONOMY_CONFIG.max_requests_per_hour,
    source_name="BrickEconomy",
)

# --- Keepa (keepa.com) ---
KEEPA_RATE_LIMITER = register_domain_limiter(
    "keepa.com",
    KEEPA_CONFIG.max_requests_per_hour,
    source_name="Keepa",
)


# ---------------------------------------------------------------------------
# Cooldown persistence
# ---------------------------------------------------------------------------

_COOLDOWN_FILE = Path.home() / ".bws" / "cooldowns.json"


def save_cooldowns() -> None:
    """Persist all domain limiter cooldown state to disk."""
    import json

    data: dict[str, dict] = {}
    for domain, limiter in _domain_registry.items():
        snap = limiter.to_snapshot()
        if snap["blocked_until_wallclock"] > 0 or snap["escalation_level"] > 0:
            data[domain] = snap

    # Include Google Trends cooldown if the module has been imported
    try:
        from services.scrape_queue.executors import get_trends_cooldown_snapshot
        trends_snap = get_trends_cooldown_snapshot()
        if trends_snap["blocked_until_wallclock"] > 0:
            data["google_trends"] = trends_snap
    except ImportError:
        pass

    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _COOLDOWN_FILE.write_text(json.dumps(data, indent=2))
    logging.getLogger("bws.cooldown").info(
        "Saved cooldown state for %d source(s)", len(data),
    )


def restore_cooldowns() -> None:
    """Restore domain limiter cooldown state from disk."""
    import json

    if not _COOLDOWN_FILE.exists():
        return

    try:
        data = json.loads(_COOLDOWN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        logging.getLogger("bws.cooldown").warning(
            "Failed to read cooldown state from %s", _COOLDOWN_FILE,
        )
        return

    for domain, snap in data.items():
        if domain == "google_trends":
            try:
                from services.scrape_queue.executors import restore_trends_cooldown_snapshot
                restore_trends_cooldown_snapshot(snap)
            except ImportError:
                pass
            continue
        limiter = _domain_registry.get(domain)
        if limiter is not None:
            limiter.restore_snapshot(snap)
