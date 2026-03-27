"""Availability analysis for Bricklink items.

Analyzes item availability and retirement status to generate an availability score.
"""

from datetime import UTC, datetime

from types.models import AnalysisScore, BricklinkItem, PricingBox


# Use UTC constant to ensure import is retained
_UTC = UTC


def _calculate_retirement_score(
    year_released: int | None,
    retirement_year: int | None = None,
) -> tuple[int, str]:
    """Calculate score based on retirement status and age."""
    current_year = datetime.now(tz=_UTC).year

    if year_released is None:
        return 50, "Release year unknown"

    age = current_year - year_released

    # If we know retirement year
    if retirement_year:
        years_retired = current_year - retirement_year
        if years_retired >= 5:
            return 90, f"Retired {years_retired} years ago - likely scarce"
        if years_retired >= 2:
            return 75, f"Retired {years_retired} years ago - becoming scarce"
        if years_retired >= 0:
            return 60, f"Recently retired ({years_retired} years) - limited availability"
        # Future retirement
        years_until = -years_retired
        if years_until <= 1:
            return 70, f"Retiring within {years_until} year(s)"
        return 40, f"Expected to retire in {years_until} years"

    # Estimate based on typical LEGO retirement cycles (2-3 years)
    if age >= 5:
        return 85, f"Released {age} years ago - likely retired and scarce"
    if age >= 3:
        return 65, f"Released {age} years ago - may be retired or retiring soon"
    if age >= 2:
        return 45, f"Released {age} years ago - likely still available"
    if age >= 1:
        return 30, f"Released {age} year(s) ago - currently available"
    return 20, "New release - widely available"


def _calculate_supply_score(current_new: PricingBox | None) -> tuple[int, str]:
    """Calculate score based on current supply indicators."""
    if not current_new:
        return 50, "No current supply data"

    total_lots = current_new.total_lots or 0
    total_qty = current_new.total_qty or 0

    # Low supply = high score (scarce = investment opportunity)
    if total_lots == 0 and total_qty == 0:
        return 95, "No current listings - extremely scarce"
    if total_lots <= 5:
        return 85, f"Very limited supply ({total_lots} lots, {total_qty} units)"
    if total_lots <= 20:
        return 65, f"Limited supply ({total_lots} lots, {total_qty} units)"
    if total_lots <= 50:
        return 45, f"Moderate supply ({total_lots} lots, {total_qty} units)"
    if total_lots <= 100:
        return 30, f"Good supply ({total_lots} lots, {total_qty} units)"
    return 15, f"Abundant supply ({total_lots} lots, {total_qty} units)"


def _calculate_price_premium_score(
    current_new: PricingBox | None,
    six_month_new: PricingBox | None,
) -> tuple[int, str]:
    """Calculate score based on price appreciation."""
    if not current_new or not six_month_new:
        return 50, "Insufficient pricing data for comparison"

    current_avg = current_new.avg_price.amount if current_new.avg_price else None
    six_month_avg = six_month_new.avg_price.amount if six_month_new.avg_price else None

    if not current_avg or not six_month_avg or six_month_avg == 0:
        return 50, "Cannot calculate price trend"

    change_pct = ((current_avg - six_month_avg) / six_month_avg) * 100

    if change_pct >= 30:
        return 90, f"Strong appreciation: +{change_pct:.0f}% in 6 months"
    if change_pct >= 15:
        return 75, f"Good appreciation: +{change_pct:.0f}% in 6 months"
    if change_pct >= 5:
        return 60, f"Slight appreciation: +{change_pct:.0f}% in 6 months"
    if change_pct >= -5:
        return 50, f"Stable pricing: {change_pct:+.0f}% in 6 months"
    if change_pct >= -15:
        return 35, f"Slight depreciation: {change_pct:.0f}% in 6 months"
    return 20, f"Significant depreciation: {change_pct:.0f}% in 6 months"


def analyze_availability(
    item: BricklinkItem,
    current_new: PricingBox | None = None,
    six_month_new: PricingBox | None = None,
    retirement_year: int | None = None,
) -> AnalysisScore | None:
    """Analyze availability and scarcity for an item.

    Args:
        item: BricklinkItem with basic info
        current_new: Current pricing data for new condition
        six_month_new: 6-month pricing data for new condition
        retirement_year: Known retirement year (optional)

    Returns:
        AnalysisScore or None if insufficient data
    """
    # Calculate component scores
    retirement_score, retirement_reason = _calculate_retirement_score(
        item.year_released,
        retirement_year,
    )
    supply_score, supply_reason = _calculate_supply_score(current_new)
    premium_score, premium_reason = _calculate_price_premium_score(
        current_new,
        six_month_new,
    )

    # Weighted average
    weights = {"retirement": 0.4, "supply": 0.35, "premium": 0.25}
    overall = int(
        retirement_score * weights["retirement"]
        + supply_score * weights["supply"]
        + premium_score * weights["premium"]
    )

    # Calculate confidence
    confidence_factors = []
    if item.year_released:
        confidence_factors.append(0.3)
    if current_new:
        confidence_factors.append(0.4)
    if six_month_new:
        confidence_factors.append(0.3)

    confidence = sum(confidence_factors)

    # Build reasoning
    reasoning = f"{retirement_reason}. {supply_reason}. {premium_reason}."

    return AnalysisScore(
        value=overall,
        confidence=confidence,
        reasoning=reasoning,
    )
