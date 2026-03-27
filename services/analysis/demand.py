"""Demand analysis for Bricklink items.

Analyzes sales volume and pricing trends to generate a demand score.
"""

from bws_types.models import AnalysisScore, MonthlySale, PricingBox


def _calculate_volume_score(sales: list[MonthlySale]) -> tuple[int, str]:
    """Calculate score based on sales volume."""
    if not sales:
        return 0, "No sales data available"

    # Calculate average monthly sales
    total_qty = sum(s.total_quantity for s in sales)
    months = len(sales)
    avg_monthly = total_qty / months if months > 0 else 0

    # Score based on average monthly volume
    if avg_monthly >= 50:
        return 95, f"Very high demand: {avg_monthly:.1f} units/month average"
    if avg_monthly >= 20:
        return 80, f"High demand: {avg_monthly:.1f} units/month average"
    if avg_monthly >= 10:
        return 65, f"Moderate demand: {avg_monthly:.1f} units/month average"
    if avg_monthly >= 5:
        return 50, f"Low demand: {avg_monthly:.1f} units/month average"
    if avg_monthly >= 1:
        return 30, f"Very low demand: {avg_monthly:.1f} units/month average"
    return 15, "Minimal sales activity"


def _calculate_trend_score(sales: list[MonthlySale]) -> tuple[int, str]:
    """Calculate score based on sales trend (recent vs older)."""
    if len(sales) < 3:
        return 50, "Insufficient data for trend analysis"

    # Sort by date (most recent first)
    sorted_sales = sorted(sales, key=lambda s: (s.year, s.month), reverse=True)

    # Compare recent (first third) vs older (last third)
    third = len(sorted_sales) // 3
    if third < 1:
        return 50, "Insufficient data for trend analysis"

    recent = sorted_sales[:third]
    older = sorted_sales[-third:]

    recent_avg = sum(s.total_quantity for s in recent) / len(recent)
    older_avg = sum(s.total_quantity for s in older) / len(older)

    if older_avg == 0:
        if recent_avg > 0:
            return 90, "New demand emerging (no older sales)"
        return 50, "No sales in comparison periods"

    change_pct = ((recent_avg - older_avg) / older_avg) * 100

    if change_pct >= 50:
        return 95, f"Strong upward trend: +{change_pct:.0f}% volume growth"
    if change_pct >= 20:
        return 80, f"Upward trend: +{change_pct:.0f}% volume growth"
    if change_pct >= -10:
        return 60, f"Stable demand: {change_pct:+.0f}% change"
    if change_pct >= -30:
        return 40, f"Declining trend: {change_pct:.0f}% volume drop"
    return 20, f"Sharp decline: {change_pct:.0f}% volume drop"


def _calculate_pricing_health(pricing: PricingBox | None) -> tuple[int, str]:
    """Calculate score based on pricing health indicators."""
    if not pricing:
        return 50, "No pricing data available"

    score = 50
    reasons = []

    # Check times sold
    if pricing.times_sold is not None:
        if pricing.times_sold >= 100:
            score += 20
            reasons.append(f"high transaction count ({pricing.times_sold})")
        elif pricing.times_sold >= 50:
            score += 10
            reasons.append(f"moderate transaction count ({pricing.times_sold})")
        elif pricing.times_sold < 10:
            score -= 10
            reasons.append(f"low transaction count ({pricing.times_sold})")

    # Check price spread (indicates healthy market)
    if pricing.min_price and pricing.max_price:
        min_amt = pricing.min_price.amount
        max_amt = pricing.max_price.amount
        if min_amt > 0:
            spread = (max_amt - min_amt) / min_amt
            if 0.1 <= spread <= 0.5:
                score += 10
                reasons.append("healthy price spread")
            elif spread > 1.0:
                score -= 5
                reasons.append("high price volatility")

    score = max(0, min(100, score))
    reason = "Pricing health: " + (", ".join(reasons) if reasons else "average")
    return score, reason


def analyze_demand(
    monthly_sales: list[MonthlySale],
    current_pricing: PricingBox | None = None,
) -> AnalysisScore | None:
    """Analyze demand for an item.

    Args:
        monthly_sales: Historical monthly sales data
        current_pricing: Current pricing box data (optional)

    Returns:
        AnalysisScore or None if insufficient data
    """
    if not monthly_sales:
        return None

    # Calculate component scores
    volume_score, volume_reason = _calculate_volume_score(monthly_sales)
    trend_score, trend_reason = _calculate_trend_score(monthly_sales)
    pricing_score, pricing_reason = _calculate_pricing_health(current_pricing)

    # Weighted average (volume most important)
    weights = {"volume": 0.5, "trend": 0.3, "pricing": 0.2}
    overall = int(
        volume_score * weights["volume"]
        + trend_score * weights["trend"]
        + pricing_score * weights["pricing"]
    )

    # Calculate confidence based on data availability
    confidence = min(1.0, len(monthly_sales) / 6)  # Full confidence at 6+ months

    # Build reasoning
    reasoning = f"{volume_reason}. {trend_reason}. {pricing_reason}."

    return AnalysisScore(
        value=overall,
        confidence=confidence,
        reasoning=reasoning,
    )
