"""Post-scrape deal notification -- checks signals and notifies on strong deals."""

import logging
from typing import TYPE_CHECKING

from services.backtesting.screener import compute_all_signals
from services.notifications.ntfy import NtfyMessage, send_notification

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.notifications.deals")

STRONG_SIGNAL_THRESHOLD = 80

# In-memory set of (set_number, eval_year, eval_month) already notified this
# process lifetime.  Prevents duplicate alerts for the same data point.
_notified: set[tuple[str, int, int]] = set()


def check_and_notify(conn: "DuckDBPyConnection") -> int:
    """Compute signals for all items and send Ntfy alerts for strong deals.

    Returns the number of new notifications sent.
    """
    signals = compute_all_signals(conn)
    sent = 0

    for item in signals:
        composite = item.get("composite_score")
        if composite is None or composite < STRONG_SIGNAL_THRESHOLD:
            continue

        set_number = item.get("set_number", "unknown")
        eval_year = item.get("eval_year", 0)
        eval_month = item.get("eval_month", 0)
        key = (set_number, eval_year, eval_month)

        if key in _notified:
            continue

        title = item.get("title") or set_number
        theme = item.get("theme") or "Unknown"
        entry_price = item.get("entry_price_cents", 0) / 100
        rrp_cents = item.get("rrp_cents")
        rrp_str = f" (RRP ${rrp_cents / 100:.0f})" if rrp_cents else ""

        msg = NtfyMessage(
            title=f"Strong Signal: {set_number} ({composite:.0f}/100)",
            message=(
                f"{title}\n"
                f"Theme: {theme}\n"
                f"Composite: {composite:.0f}/100\n"
                f"Entry price: ${entry_price:.2f}{rrp_str}\n"
                f"Data: {eval_year}-{eval_month:02d}"
            ),
        )

        if send_notification(msg):
            _notified.add(key)
            sent += 1

    if sent:
        logger.info("Sent %d strong-deal notifications", sent)

    return sent
