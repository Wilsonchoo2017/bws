"""Shared HTTP utilities for scrapers."""

from config.settings import get_random_accept_language, get_random_user_agent


def get_browser_headers(
    *,
    referer: str | None = None,
    accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Generate randomized browser-like HTTP headers.

    Args:
        referer: Optional Referer header value.
        accept: Accept header value (default is standard browser accept).
        extra: Additional headers to merge (e.g. Upgrade-Insecure-Requests).
    """
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": accept,
        "Accept-Language": get_random_accept_language(),
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    if extra:
        headers = {**headers, **extra}
    return headers
