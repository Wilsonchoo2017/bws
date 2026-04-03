"""Browser configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserConfig:
    """Configuration for a persistent browser session."""

    profile_name: str
    headless: bool = True
    locale: str = "en-US"
    window: tuple[int, int] = (1366, 768)
