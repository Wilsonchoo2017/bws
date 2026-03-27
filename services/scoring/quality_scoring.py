"""Quality scoring service.

4-component weighted scoring system for quality analysis.
"""

from config.value_investing import (
    DEFAULT_THEME_MULTIPLIER,
    PPD_EXCELLENT,
    PPD_FAIR,
    PPD_GOOD,
    QUALITY_SCORE_WEIGHTS,
    THEME_MULTIPLIERS,
)
from types.models import QualityScoreBreakdown
from types.price import Cents, cents_to_dollars


def _calculate_ppd_score(
    parts_count: int | None,
    msrp_cents: Cents | None,
) -> int:
    """Calculate PPD (parts per dollar) component score (0-100).

    Based on value ratio of parts to price.
    """
    if parts_count is None or msrp_cents is None or msrp_cents <= 0:
        return 50  # Neutral when no data

    msrp_dollars = cents_to_dollars(msrp_cents)
    ppd = parts_count / msrp_dollars

    # Score based on PPD thresholds
    if ppd >= PPD_EXCELLENT:
        return 95
    if ppd >= PPD_GOOD:
        return 80
    if ppd >= PPD_FAIR:
        return 60
    if ppd >= 4.0:
        return 40
    return 25


def _calculate_complexity_score(
    parts_count: int | None,
) -> int:
    """Calculate complexity component score (0-100).

    Based on set size/complexity (more parts = more complex/valuable).
    """
    if parts_count is None:
        return 50  # Neutral when no data

    # Score based on parts count
    if parts_count >= 5000:
        return 100  # Massive sets (UCS, modular)
    if parts_count >= 3000:
        return 90
    if parts_count >= 2000:
        return 80
    if parts_count >= 1000:
        return 70
    if parts_count >= 500:
        return 55
    if parts_count >= 200:
        return 40
    return 30


def _calculate_theme_score(theme: str | None) -> int:
    """Calculate theme component score (0-100).

    Based on theme's collector appeal and market performance.
    """
    if not theme:
        return 50  # Neutral when no data

    # Get theme multiplier
    multiplier = DEFAULT_THEME_MULTIPLIER

    # Exact match
    if theme in THEME_MULTIPLIERS:
        multiplier = THEME_MULTIPLIERS[theme]
    else:
        # Partial match
        theme_lower = theme.lower()
        for key, value in THEME_MULTIPLIERS.items():
            if key.lower() in theme_lower or theme_lower in key.lower():
                multiplier = value
                break

    # Convert multiplier to score (0.5 -> 25, 1.0 -> 50, 1.5 -> 75)
    score = int((multiplier - 0.5) * 100)
    return max(0, min(100, score))


def _calculate_scarcity_score(
    available_lots: int | None,
) -> int:
    """Calculate scarcity component score (0-100).

    Based on number of sellers (fewer = more scarce).
    """
    if available_lots is None:
        return 50  # Neutral when no data

    # Score based on lot count (inverse relationship)
    if available_lots < 3:
        return 95  # Very scarce
    if available_lots < 10:
        return 80
    if available_lots < 25:
        return 60
    if available_lots < 50:
        return 45
    if available_lots < 100:
        return 30
    return 20  # Very common


def calculate_quality_score(
    parts_count: int | None = None,
    msrp_cents: Cents | None = None,
    theme: str | None = None,
    available_lots: int | None = None,
) -> QualityScoreBreakdown:
    """Calculate 4-component quality score with breakdown.

    Components and weights:
    - PPD: 40% - Parts per dollar value
    - Complexity: 30% - Set size/complexity
    - Theme: 20% - Theme collector appeal
    - Scarcity: 10% - Market scarcity

    Args:
        parts_count: Number of parts in the set
        msrp_cents: MSRP in cents
        theme: Theme name
        available_lots: Number of sellers

    Returns:
        QualityScoreBreakdown with component scores and final score
    """
    # Calculate component scores
    ppd_score = _calculate_ppd_score(parts_count, msrp_cents)
    complexity_score = _calculate_complexity_score(parts_count)
    theme_score = _calculate_theme_score(theme)
    scarcity_score = _calculate_scarcity_score(available_lots)

    # Calculate weighted final score
    weights = QUALITY_SCORE_WEIGHTS
    final_score = int(
        ppd_score * weights.ppd
        + complexity_score * weights.complexity
        + theme_score * weights.theme
        + scarcity_score * weights.scarcity
    )

    # Calculate confidence based on data availability
    data_points = sum(
        [
            parts_count is not None,
            msrp_cents is not None,
            theme is not None,
            available_lots is not None,
        ]
    )
    confidence = min(1.0, data_points / 4)

    return QualityScoreBreakdown(
        ppd_score=ppd_score,
        complexity_score=complexity_score,
        theme_score=theme_score,
        scarcity_score=scarcity_score,
        final_score=final_score,
        confidence=confidence,
    )
