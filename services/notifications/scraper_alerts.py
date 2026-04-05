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


def alert_rate_limited(source: str, cooldown_minutes: float, level: int) -> None:
    """Alert when a source hits rate limiting (429)."""
    key = f"rate_limited:{source}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"{source}: Rate Limited (level {level})",
        message=(
            f"{source} hit rate limit.\n"
            f"Cooldown: {cooldown_minutes:.0f} min\n"
            f"Escalation level: {level}"
        ),
        priority=3,  # default
        tags=("warning", "hourglass"),
        topic=NTFY_TOPIC_ALERTS,
    ))


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


def alert_recovered(source: str) -> None:
    """Alert when a source recovers after being blocked."""
    key = f"recovered:{source}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"{source}: Recovered",
        message=f"{source} is working again after being blocked.",
        priority=2,  # low
        tags=("white_check_mark",),
        topic=NTFY_TOPIC_ALERTS,
    ))


def alert_rest_period(source: str, rest_minutes: float, scrape_hours: float) -> None:
    """Alert when mandatory rest period kicks in."""
    key = f"rest:{source}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"{source}: Mandatory Rest Period",
        message=(
            f"{source} scraped for {scrape_hours:.1f}h continuously.\n"
            f"Resting for {rest_minutes:.0f} min to avoid ban."
        ),
        priority=2,  # low
        tags=("zzz",),
        topic=NTFY_TOPIC_ALERTS,
    ))


def alert_cloudflare_blocked(
    source: str,
    consecutive_challenges: int,
    set_number: str | None = None,
) -> None:
    """Alert when repeated Cloudflare challenges indicate a block."""
    key = f"cf_blocked:{source}"
    if not _should_send(key):
        return

    context = f" (last set: {set_number})" if set_number else ""
    send_notification(NtfyMessage(
        title=f"{source}: Cloudflare Blocking ({consecutive_challenges}x)",
        message=(
            f"{source} hit {consecutive_challenges} consecutive "
            f"Cloudflare challenges{context}.\n"
            "Browser profile may be flagged or IP is suspect.\n"
            "Consider clearing the profile or rotating IP."
        ),
        priority=4,  # high
        tags=("warning", "shield"),
        topic=NTFY_TOPIC_ALERTS,
    ))


def alert_source_cooldown(source: str, cooldown_seconds: float) -> None:
    """Alert when any scrape-queue source enters cooldown."""
    key = f"source_cooldown:{source}"
    if not _should_send(key):
        return

    minutes = cooldown_seconds / 60
    send_notification(NtfyMessage(
        title=f"{source}: Cooldown ({minutes:.0f}m)",
        message=(
            f"{source} entered cooldown.\n"
            f"Sleeping for {minutes:.0f} min before retrying."
        ),
        priority=3,  # default
        tags=("hourglass",),
        topic=NTFY_TOPIC_ALERTS,
    ))


def alert_keepa_cooldown(
    set_number: str,
    failure_count: int,
    cooldown_hours: int,
) -> None:
    """Alert when a Keepa set enters failure cooldown."""
    key = f"keepa_cooldown:{set_number}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"Keepa: {set_number} on cooldown",
        message=(
            f"Set {set_number} failed {failure_count} times consecutively.\n"
            f"On cooldown for {cooldown_hours}h before next retry."
        ),
        priority=3,  # default
        tags=("hourglass",),
        topic=NTFY_TOPIC_ALERTS,
    ))


def alert_keepa_recovered(set_number: str) -> None:
    """Alert when a Keepa set recovers after previous failures."""
    key = f"keepa_recovered:{set_number}"
    if not _should_send(key):
        return

    send_notification(NtfyMessage(
        title=f"Keepa: {set_number} recovered",
        message=f"Set {set_number} scraped successfully after previous failures.",
        priority=2,  # low
        tags=("white_check_mark",),
        topic=NTFY_TOPIC_ALERTS,
    ))
