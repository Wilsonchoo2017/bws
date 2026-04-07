"""BWS configuration."""

from config.settings import (
    ACCEPT_LANGUAGES,
    RATE_LIMIT_CONFIG,
    RETRY_CONFIG,
    USER_AGENTS,
    get_random_accept_language,
    get_random_delay,
    get_random_user_agent,
)


__all__ = [
    "ACCEPT_LANGUAGES",
    "RATE_LIMIT_CONFIG",
    "RETRY_CONFIG",
    "USER_AGENTS",
    "get_random_accept_language",
    "get_random_delay",
    "get_random_user_agent",
]
