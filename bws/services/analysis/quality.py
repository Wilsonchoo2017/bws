"""Quality analysis for Bricklink items.

Analyzes item quality using the 4-component scoring system.
"""

from bws.services.scoring.quality_scoring import calculate_quality_score
from bws.types.models import AnalysisScore
from bws.types.price import Cents


def analyze_quality(
    parts_count: int | None = None,
    msrp_cents: Cents | None = None,
    theme: str | None = None,
    available_lots: int | None = None,
) -> AnalysisScore | None:
    """Analyze quality for an item.

    Uses the 4-component quality scoring system:
    - PPD (40%): Parts per dollar value
    - Complexity (30%): Set size/complexity
    - Theme (20%): Theme collector appeal
    - Scarcity (10%): Market scarcity

    Args:
        parts_count: Number of parts in the set
        msrp_cents: MSRP in cents
        theme: Theme name
        available_lots: Number of sellers

    Returns:
        AnalysisScore or None if no data available
    """
    # Check if we have any data
    if all(v is None for v in [parts_count, msrp_cents, theme, available_lots]):
        return None

    # Calculate quality score breakdown
    breakdown = calculate_quality_score(
        parts_count=parts_count,
        msrp_cents=msrp_cents,
        theme=theme,
        available_lots=available_lots,
    )

    # Build reasoning from component scores
    reasons = []

    if parts_count is not None:
        reasons.append(f"Complexity: {breakdown.complexity_score}/100")

    if parts_count is not None and msrp_cents is not None:
        reasons.append(f"PPD value: {breakdown.ppd_score}/100")

    if theme is not None:
        reasons.append(f"Theme appeal: {breakdown.theme_score}/100")

    if available_lots is not None:
        reasons.append(f"Scarcity: {breakdown.scarcity_score}/100")

    reasoning = ". ".join(reasons) if reasons else "Quality analysis based on available data"

    return AnalysisScore(
        value=breakdown.final_score,
        confidence=breakdown.confidence,
        reasoning=reasoning,
    )
