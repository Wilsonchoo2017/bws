"""Monthly cumulative profit history from actual transactions.

No market valuations -- purely cash-based:
  - BUY  = cash out (negative)
  - SELL = cash in  (positive)
  - Net profit = cumulative sells - cumulative buys

Returns 24 months to support YoY comparison.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def get_profit_history(conn: Any, months: int = 24) -> list[dict]:
    """Return monthly cumulative profit from transactions.

    Each row contains:
      - cumulative_buy_cents:  total spent on BUYs up to that month-end
      - cumulative_sell_cents: total earned from SELLs up to that month-end
      - net_profit_cents:      sells - buys (negative = more invested than earned)
      - month_buy_cents:       BUY spend in that single month
      - month_sell_cents:      SELL revenue in that single month
    """
    now = datetime.now(tz=timezone.utc)

    # Build month-end list
    month_ends: list[tuple[int, int]] = []
    y, m = now.year, now.month
    for _ in range(months):
        month_ends.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_ends.reverse()

    # Aggregate transactions by (year, month, txn_type)
    rows = conn.execute(
        """
        SELECT
            EXTRACT(YEAR FROM txn_date)::int  AS yr,
            EXTRACT(MONTH FROM txn_date)::int AS mo,
            txn_type,
            SUM(quantity * price_cents)        AS total_cents
        FROM portfolio_transactions
        GROUP BY yr, mo, txn_type
        ORDER BY yr, mo
        """
    ).fetchall()

    # Build lookup: (year, month) -> {BUY: cents, SELL: cents}
    monthly: dict[tuple[int, int], dict[str, int]] = {}
    for yr, mo, txn_type, total_cents in rows:
        key = (int(yr), int(mo))
        monthly.setdefault(key, {"BUY": 0, "SELL": 0})
        monthly[key][txn_type] = int(total_cents)

    # Walk through months, accumulate
    cum_buy = 0
    cum_sell = 0
    results: list[dict] = []

    # We need cumulative totals from the beginning, so first sum everything
    # before our window starts
    first_year, first_month = month_ends[0]
    for (yr, mo), amounts in monthly.items():
        if yr < first_year or (yr == first_year and mo < first_month):
            cum_buy += amounts["BUY"]
            cum_sell += amounts["SELL"]

    for year, month in month_ends:
        key = (year, month)
        month_buy = monthly.get(key, {}).get("BUY", 0)
        month_sell = monthly.get(key, {}).get("SELL", 0)

        cum_buy += month_buy
        cum_sell += month_sell

        results.append({
            "year": year,
            "month": month,
            "date": f"{year}-{month:02d}",
            "cumulative_buy_cents": cum_buy,
            "cumulative_sell_cents": cum_sell,
            "net_profit_cents": cum_sell - cum_buy,
            "month_buy_cents": month_buy,
            "month_sell_cents": month_sell,
        })

    return results
