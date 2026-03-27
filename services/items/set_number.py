"""Extract LEGO set numbers from product titles."""

import re

# LEGO set numbers are 4-6 digits, sometimes with a -1 suffix
_SET_NUMBER_RE = re.compile(r"\b(\d{4,6})(?:-\d)?\b")

# Years to exclude (false positives)
_YEAR_RANGE = set(range(1990, 2035))


def extract_set_number(title: str) -> str | None:
    """Extract a LEGO set number from a product title.

    Finds 4-6 digit numbers that aren't years or piece counts.

    Examples:
        "LEGO Star Wars 75192 Millennium Falcon (7541 Pcs)" -> "75192"
        "LEGO 42151 Technic Bugatti Bolide" -> "42151"
        "LEGO Icons 10497 Galaxy Explorer" -> "10497"
        "Random toy with no set number" -> None
    """
    matches = _SET_NUMBER_RE.findall(title)
    for match in matches:
        num = int(match)
        if num in _YEAR_RANGE:
            continue
        # Skip piece counts -- usually preceded by "(" or followed by "Pieces"/"Pcs"
        idx = title.find(match)
        if idx > 0:
            before = title[max(0, idx - 2) : idx]
            after_end = idx + len(match)
            after = title[after_end : after_end + 10].lower()
            if "(" in before and ("piece" in after or "pcs" in after):
                continue
        if num >= 1000:
            return match
    return None
