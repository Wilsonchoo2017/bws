"""Extract LEGO set numbers from Reddit text.

Strategy:
1. Regex-scan for 4-7 digit integers (LEGO sets are 4-6 digits; some
   modern sets touch 7). Allow optional "-1" suffix for set variant.
2. Intersect the candidate numbers with a known-set catalog loaded
   from `lego_items.set_number` so we only emit real matches.

False positives we care about:
- Years (1995, 2024, etc.) -- filtered by catalog lookup.
- Prices ($299, 4999 yen) -- same, catalog filter removes them.
- Piece counts ("1,234 pieces") -- same.

We deliberately do *not* require "LEGO" or "set" nearby; most LEGO-sub
posts are already contextual, and requiring a keyword would miss a lot
of mentions (titles like "21322 review" are very common).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("bws.reddit.extractor")


# 4 to 7 digits, optionally followed by -1 or -2 variant suffix.
# Surrounded by word boundaries so we don't match inside longer numbers.
_SET_NUMBER_RE = re.compile(r"\b(\d{4,7})(?:-\d{1,2})?\b")

# Obviously-not-a-set numbers to skip before catalog lookup.
# Years from 1950-2099 are the main false-positive class; we strip them
# early to avoid a giant catalog miss-list for everything retired in
# e.g. "retired in 2019" posts.
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20\d{2})\b")


@dataclass(frozen=True)
class MentionMatch:
    """A single set-number hit inside a text blob."""

    set_number: str
    start: int
    end: int


def extract_candidates(text: str) -> list[str]:
    """Return distinct 4-7 digit candidate numbers found in `text`.

    Candidates are NOT yet filtered against the catalog -- that happens
    in `extract_mentions` below.
    """
    if not text:
        return []

    seen: set[str] = set()
    candidates: list[str] = []
    for match in _SET_NUMBER_RE.finditer(text):
        number = match.group(1)
        if number in seen:
            continue
        # Skip obvious years -- a candidate like "2019" is never going
        # to be a set number and is noisy at the catalog-lookup stage.
        if _YEAR_RE.fullmatch(number):
            continue
        seen.add(number)
        candidates.append(number)
    return candidates


def extract_mentions(
    text: str,
    known_set_numbers: frozenset[str],
) -> list[MentionMatch]:
    """Return mention matches filtered against the known-set catalog.

    Args:
        text: Post title + body, or comment body.
        known_set_numbers: Set of valid LEGO set_number strings.

    Returns:
        List of `MentionMatch` with character offsets. Deduplicated by
        set_number (first occurrence wins for offsets).
    """
    if not text or not known_set_numbers:
        return []

    seen: set[str] = set()
    out: list[MentionMatch] = []
    for match in _SET_NUMBER_RE.finditer(text):
        number = match.group(1)
        if number in seen:
            continue
        if _YEAR_RE.fullmatch(number):
            continue
        if number not in known_set_numbers:
            continue
        seen.add(number)
        out.append(
            MentionMatch(
                set_number=number,
                start=match.start(),
                end=match.end(),
            )
        )
    return out


def load_known_set_numbers(conn) -> frozenset[str]:  # noqa: ANN001
    """Load the full set of valid set_number strings from lego_items.

    Cached by the caller -- the catalog is ~2000 entries and only
    changes when we onboard new sets, so one load per scraper run
    is enough.
    """
    rows = conn.execute(
        "SELECT DISTINCT set_number FROM lego_items "
        "WHERE set_number IS NOT NULL"
    ).fetchall()
    return frozenset(row[0] for row in rows if row[0])
