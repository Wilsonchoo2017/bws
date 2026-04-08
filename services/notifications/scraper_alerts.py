"""Scraper health alerts via Ntfy.

Sends notifications when scrapers hit rate limits, bans, or sustained
failures so the operator knows without checking logs.
"""

import logging
import time

from services.notifications.ntfy import NTFY_TOPIC_ALERTS, NtfyMessage, send_notification

logger = logging.getLogger("bws.notifications.scraper_alerts")

# Throttle: don't send the same alert type more than once per interval.
_THROTTLE_SECONDS = 3600.0  # 1 hour between identical alert types
_last_sent: dict[str, float] = {}


def _should_send(alert_key: str) -> bool:
    """Check if enough time has passed since the last alert of this type."""
    now = time.monotonic()
    last = _last_sent.get(alert_key, 0.0)
    if now - last < _THROTTLE_SECONDS:
        return False
    _last_sent[alert_key] = now
    return True


def alert_forbidden(source: str, cooldown_minutes: float, level: int) -> None:
    """Alert when a source returns 403 Forbidden (IP ban)."""
    key = f"forbidden:{source}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"{source}: 403 Forbidden / IP Banned",
        message=(
            f"{source} returned 403 Forbidden.\n"
            f"IP appears to be banned.\n"
            f"Cooldown: {cooldown_minutes:.0f} min (level {level})\n"
            f"Check: curl -L 'https://www.bricklink.com/catalogPG.asp?S=10255-1'"
        ),
        priority=5,  # urgent
        tags=("rotating_light", "no_entry"),
        topic=NTFY_TOPIC_ALERTS,
    ))


def alert_silent_ban(source: str, consecutive_failures: int, cooldown_minutes: float) -> None:
    """Alert when consecutive empty responses suggest a silent ban."""
    key = f"silent_ban:{source}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"{source}: Silent Ban Detected",
        message=(
            f"{source} returned {consecutive_failures} consecutive empty responses.\n"
            f"Likely serving block/error page instead of data.\n"
            f"Cooldown: {cooldown_minutes:.0f} min"
        ),
        priority=4,  # high
        tags=("warning", "ghost"),
        topic=NTFY_TOPIC_ALERTS,
    ))



