"""Google Trends scraper using trendspy."""

import logging
import time
from datetime import datetime, timezone

from services.google_trends.types import TrendsData, TrendsDataPoint, TrendsScrapeResult

logger = logging.getLogger("bws.google_trends.scraper")

# Delay between requests to avoid Google rate limiting (seconds).
REQUEST_DELAY_SECONDS = 5
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 60

# Default lookback if no release year is known.
DEFAULT_LOOKBACK_YEARS = 5


def _build_timeframe(year_released: int | None) -> tuple[str, str]:
    """Return (start_date, end_date) strings for the Trends query."""
    today = datetime.now(tz=timezone.utc).date()
    end_date = today.strftime("%Y-%m-%d")

    if year_released:
        start_date = f"{year_released}-01-01"
    else:
        start_year = today.year - DEFAULT_LOOKBACK_YEARS
        start_date = f"{start_year}-01-01"

    return start_date, end_date


def fetch_interest(
    set_number: str,
    year_released: int | None = None,
    search_property: str = "youtube",
    geo: str = "",
) -> TrendsScrapeResult:
    """Fetch Google Trends interest-over-time for a LEGO set.

    Args:
        set_number: LEGO set number (e.g. "31113").
        year_released: Release year for timeframe start. Falls back to 5-year lookback.
        search_property: Google property -- "youtube", "", "news", "images", "froogle".
        geo: Geographic filter -- "" for worldwide, or country code like "US".

    Returns:
        TrendsScrapeResult with interest data or error details.
    """
    keyword = f"LEGO {set_number}"
    start_date, end_date = _build_timeframe(year_released)
    timeframe = f"{start_date} {end_date}"

    logger.info(
        "Fetching trends for %r, property=%s, geo=%r, timeframe=%s",
        keyword,
        search_property,
        geo,
        timeframe,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            from trendspy import Trends

            tr = Trends()
            df = tr.interest_over_time(
                keywords=[keyword],
                gprop=search_property,
                geo=geo,
                timeframe=timeframe,
            )

            if df.empty:
                logger.warning("No data returned for %s", keyword)
                return TrendsScrapeResult(
                    success=True,
                    set_number=set_number,
                    data=TrendsData(
                        set_number=set_number,
                        keyword=keyword,
                        search_property=search_property,
                        geo=geo,
                        timeframe_start=start_date,
                        timeframe_end=end_date,
                        interest_over_time=(),
                        peak_value=None,
                        peak_date=None,
                        average_value=None,
                        scraped_at=datetime.now(tz=timezone.utc),
                    ),
                )

            # Convert DataFrame rows to immutable data points.
            points: list[TrendsDataPoint] = []
            for ts, row in df.iterrows():
                date_str = ts.strftime("%Y-%m-%d")
                value = int(row[keyword])
                points.append(TrendsDataPoint(date=date_str, value=value))

            series = df[keyword]
            peak_value = int(series.max())
            peak_idx = series.idxmax()
            peak_date = peak_idx.strftime("%Y-%m-%d") if peak_value > 0 else None
            average_value = round(float(series.mean()), 2)

            data = TrendsData(
                set_number=set_number,
                keyword=keyword,
                search_property=search_property,
                geo=geo,
                timeframe_start=start_date,
                timeframe_end=end_date,
                interest_over_time=tuple(points),
                peak_value=peak_value,
                peak_date=peak_date,
                average_value=average_value,
                scraped_at=datetime.now(tz=timezone.utc),
            )

            logger.info(
                "Got %d data points for %s (peak=%d at %s, avg=%.1f)",
                len(points),
                keyword,
                peak_value,
                peak_date,
                average_value,
            )

            return TrendsScrapeResult(
                success=True,
                set_number=set_number,
                data=data,
            )

        except Exception as exc:
            error_str = str(exc)
            is_rate_limit = "429" in error_str or "Too Many" in error_str
            logger.warning(
                "Attempt %d/%d failed for %s: %s",
                attempt,
                MAX_RETRIES,
                keyword,
                error_str,
            )
            if attempt < MAX_RETRIES and is_rate_limit:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.info("Rate limited, waiting %ds before retry", wait)
                time.sleep(wait)
                continue

            return TrendsScrapeResult(
                success=False,
                set_number=set_number,
                error=f"Failed after {attempt} attempts: {error_str}",
            )

    # Should not reach here, but satisfy type checker.
    return TrendsScrapeResult(
        success=False,
        set_number=set_number,
        error="Exhausted retries",
    )
