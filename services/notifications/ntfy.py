"""Ntfy notification client."""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("bws.notifications.ntfy")

NTFY_BASE_URL = "https://dxp.tail83c2f.ts.net:8093"
NTFY_TOPIC = "bws-deals"


@dataclass(frozen=True)
class NtfyMessage:
    """A single Ntfy notification."""

    title: str
    message: str
    priority: int = 4  # high
    tags: tuple[str, ...] = ("chart_with_upwards_trend", "money_with_wings")


def send_notification(msg: NtfyMessage) -> bool:
    """Send a notification to Ntfy. Returns True on success."""
    url = NTFY_BASE_URL
    payload = {
        "topic": NTFY_TOPIC,
        "title": msg.title,
        "message": msg.message,
        "priority": msg.priority,
        "tags": list(msg.tags),
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10, verify=False)
        resp.raise_for_status()
        logger.info("Ntfy notification sent: %s", msg.title)
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send Ntfy notification: %s", msg.title)
        return False
