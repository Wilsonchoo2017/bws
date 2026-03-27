"""Theme multiplier calculator.

Calculates theme performance multiplier based on LEGO theme.
"""

from config.value_investing import (
    DEFAULT_THEME_MULTIPLIER,
    THEME_MULTIPLIERS,
)
from types.models import MultiplierResult


def calculate_theme_multiplier(theme: str | None) -> MultiplierResult:
    """Calculate theme performance multiplier.

    Uses THEME_MULTIPLIERS lookup with partial matching.
    Premium themes (Star Wars, Architecture) get higher multipliers.
    Lower demand themes (City, Friends) get lower multipliers.

    Args:
        theme: Theme name or None

    Returns:
        MultiplierResult with theme multiplier
    """
    if not theme:
        return MultiplierResult(
            multiplier=DEFAULT_THEME_MULTIPLIER,
            explanation="No theme data available",
            applied=False,
            data_used=(("theme", None),),
        )

    # Exact match first
    if theme in THEME_MULTIPLIERS:
        multiplier = THEME_MULTIPLIERS[theme]
        return MultiplierResult(
            multiplier=multiplier,
            explanation=f"{theme} theme ({_describe_multiplier(multiplier)})",
            applied=True,
            data_used=(("theme", theme),),
        )

    # Partial match (case-insensitive)
    theme_lower = theme.lower()
    for key, multiplier in THEME_MULTIPLIERS.items():
        if key.lower() in theme_lower or theme_lower in key.lower():
            return MultiplierResult(
                multiplier=multiplier,
                explanation=f"{theme} (matched: {key}) ({_describe_multiplier(multiplier)})",
                applied=True,
                data_used=(
                    ("theme", theme),
                    ("matched_theme", key),
                ),
            )

    # No match found
    return MultiplierResult(
        multiplier=DEFAULT_THEME_MULTIPLIER,
        explanation=f"Unknown theme: {theme}",
        applied=True,
        data_used=(("theme", theme),),
    )


def _describe_multiplier(multiplier: float) -> str:
    """Describe a theme multiplier for explanation text."""
    if multiplier >= 1.30:
        return "premium theme"
    if multiplier >= 1.15:
        return "strong theme"
    if multiplier >= 1.05:
        return "above average"
    if multiplier >= 0.95:
        return "average"
    if multiplier >= 0.80:
        return "below average"
    return "weak theme"
