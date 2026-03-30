"""BWS configuration settings.

Rate limiting, user agents, and other scraper configuration.
"""


import secrets
from dataclasses import dataclass
from pathlib import Path


# Database path (isolated from MoonBridge)
BWS_DB_PATH = Path.home() / ".bws" / "bws.duckdb"


@dataclass(frozen=True)
class RateLimitSettings:
    """Rate limiting configuration."""

    min_delay_ms: int = 10_000  # 10 seconds
    max_delay_ms: int = 30_000  # 30 seconds
    max_requests_per_hour: int = 15


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


def calculate_backoff(attempt: int) -> float:
    """Calculate exponential backoff delay in seconds.

    Args:
        attempt: Attempt number (1-based)

    Returns:
        Backoff delay in seconds
    """
    delay_ms = RETRY_CONFIG.initial_backoff_ms * (RETRY_CONFIG.backoff_multiplier ** (attempt - 1))
    return min(delay_ms, RETRY_CONFIG.max_backoff_ms) / 1000.0
