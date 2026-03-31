"""BWS configuration settings.

Rate limiting, user agents, and other scraper configuration.
"""


import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path


# Database path (isolated from MoonBridge)
BWS_DB_PATH = Path.home() / ".bws" / "bws.duckdb"

# Local image storage
BWS_IMAGES_PATH = Path.home() / ".bws" / "images"
BWS_IMAGES_SETS_PATH = BWS_IMAGES_PATH / "sets"
BWS_IMAGES_MINIFIGS_PATH = BWS_IMAGES_PATH / "minifigs"
BWS_IMAGES_PARTS_PATH = BWS_IMAGES_PATH / "parts"


@dataclass(frozen=True)
class RateLimitSettings:
    """Rate limiting configuration."""

    min_delay_ms: int = 5_000  # 5 seconds
    max_delay_ms: int = 15_000  # 15 seconds
    max_requests_per_hour: int = 1_000


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
    """Sliding-window rate limiter with quota-exceeded circuit breaker.

    Tracks request timestamps and enforces max requests per hour.
    When trip_quota_exceeded() is called, blocks all requests for 1 hour.
    """

    COOLDOWN_SECONDS = 3600.0  # 1 hour

    def __init__(self, max_per_hour: int) -> None:
        self._max_per_hour = max_per_hour
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()
        self._blocked_until: float = 0.0

    def _prune(self, now: float) -> None:
        """Remove timestamps older than 1 hour."""
        cutoff = now - 3600.0
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.pop(0)

    def trip_quota_exceeded(self) -> None:
        """Block all requests for 1 hour starting now."""
        self._blocked_until = time.monotonic() + self.COOLDOWN_SECONDS
        logging.getLogger("bws.bricklink").warning(
            "Quota exceeded — pausing BrickLink requests for 1 hour"
        )

    def is_blocked(self) -> bool:
        """Check if the limiter is currently in cooldown."""
        return time.monotonic() < self._blocked_until

    async def acquire(self) -> None:
        """Wait until a request slot is available, then record it."""
        async with self._lock:
            now = time.monotonic()

            # Wait out quota cooldown if active
            if now < self._blocked_until:
                wait = self._blocked_until - now
                logging.getLogger("bws.bricklink").info(
                    "BrickLink quota cooldown: %.0fs remaining", wait,
                )
                await asyncio.sleep(wait)
                now = time.monotonic()

            self._prune(now)

            if len(self._timestamps) >= self._max_per_hour:
                wait = self._timestamps[0] - (now - 3600.0)
                if wait > 0:
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                    self._prune(now)

            self._timestamps.append(now)


BRICKLINK_RATE_LIMITER = HourlyRateLimiter(RATE_LIMIT_CONFIG.max_requests_per_hour)


@dataclass(frozen=True)
class BrickeconomySettings:
    """BrickEconomy browser automation configuration."""

    base_url: str = "https://www.brickeconomy.com"
    headless: bool = False
    timeout_ms: int = 30_000
    locale: str = "en-US"
    captcha_timeout_s: int = 120
    min_delay_ms: int = 8_000
    max_delay_ms: int = 20_000
    max_requests_per_hour: int = 60


BRICKECONOMY_CONFIG = BrickeconomySettings()
BRICKECONOMY_RATE_LIMITER = HourlyRateLimiter(
    BRICKECONOMY_CONFIG.max_requests_per_hour
)
KEEPA_RATE_LIMITER = HourlyRateLimiter(KEEPA_CONFIG.max_requests_per_hour)
