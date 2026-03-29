"""Modifier computation functions for backtesting.

Modifiers are multipliers (centered at 1.0) that adjust signal effectiveness.
"""

from config.value_investing import THEME_MULTIPLIERS, get_theme_multiplier

# Subthemes that command premium prices
PREMIUM_SUBTHEMES: dict[str, float] = {
    "Ultimate Collector Series": 1.20,
    "UCS": 1.20,
    "Modular Buildings": 1.15,
    "Creator Expert": 1.10,
    "Architecture": 1.10,
    "Ideas": 1.05,
    "Icons": 1.05,
    "Art": 1.05,
}

# Themes with niche penalty (small collector base)
NICHE_THEMES: dict[str, float] = {
    "Vidiyo": 0.70,
    "Dots": 0.80,
    "Duplo": 0.85,
    "Classic": 0.85,
    "Friends": 0.90,
}


def compute_shelf_life(
    year_released: int | None,
    year_retired: int | None,
) -> float:
    """Modifier B: Shelf life duration.

    Shorter shelf life = rarer set = higher modifier.
    """
    if year_released is None or year_retired is None:
        return 1.0

    shelf_life = year_retired - year_released

    if shelf_life <= 1:
        return 1.15  # Very short production run
    if shelf_life <= 2:
        return 1.10
    if shelf_life <= 3:
        return 1.0  # Typical
    if shelf_life <= 5:
        return 0.95
    return 0.90  # Very long production - likely mass-market


def compute_subtheme_premium(theme: str | None) -> float:
    """Modifier C: Subtheme premium multiplier."""
    if theme is None:
        return 1.0

    # Check exact match
    if theme in PREMIUM_SUBTHEMES:
        return PREMIUM_SUBTHEMES[theme]

    # Partial match
    theme_lower = theme.lower()
    for key, value in PREMIUM_SUBTHEMES.items():
        if key.lower() in theme_lower or theme_lower in key.lower():
            return value

    return 1.0


def compute_niche_penalty(theme: str | None) -> float:
    """Modifier D: Niche penalty for low-demand themes."""
    if theme is None:
        return 1.0

    if theme in NICHE_THEMES:
        return NICHE_THEMES[theme]

    theme_lower = theme.lower()
    for key, value in NICHE_THEMES.items():
        if key.lower() in theme_lower or theme_lower in key.lower():
            return value

    return 1.0
