"""Shopee captcha detection: multi-signal, snapshot storage, event recording.

Detection uses three independent signals:
  - URL match: page URL contains a known verify/captcha fragment
  - DOM match: page has elements with captcha/verify class or id selectors
  - Text match: page body text contains a known anti-bot phrase

A captcha is considered detected if ANY signal fires. The signals dict is
persisted to the snapshot meta.json AND to the shopee_captcha_events table
so we can retroactively diagnose false negatives from real snapshots.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger("bws.shopee.captcha_detection")

# Directory where captcha snapshots are stored for future analysis
SNAPSHOT_DIR = Path(__file__).resolve().parent / "captcha_snapshots"

# URL fragments / page indicators that signal a captcha or verification challenge
_CAPTCHA_URL_PATTERNS: tuple[str, ...] = (
    "/verify/",
    "/captcha",
    "security-check",
    "challenge",
)

# Phrases that typically appear on Shopee captcha / bot-challenge pages.
# Compared case-insensitively against body innerText.
_CAPTCHA_TEXT_PATTERNS: tuple[str, ...] = (
    "verify it's you",
    "verify it is you",
    "confirm you're not a robot",
    "confirm you are not a robot",
    "security verification",
    "please verify",
    "prove you're human",
    "suspicious activity",
    "unusual traffic",
    "人机验证",
    "请完成验证",
    "verifikasi keamanan",
)


@dataclass(frozen=True)
class CaptchaSignals:
    """Aggregated captcha detection signals for a single page check."""

    url: str = ""
    url_match: bool = False
    dom_match: bool = False
    text_match: bool = False
    matched_url_pattern: str | None = None
    matched_dom_selectors: tuple[str, ...] = ()
    matched_text_phrases: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return self.url_match or self.dom_match or self.text_match

    @property
    def reason(self) -> str:
        """A short label describing which signal(s) fired."""
        parts: list[str] = []
        if self.url_match:
            parts.append("url_match")
        if self.dom_match:
            parts.append("dom_match")
        if self.text_match:
            parts.append("text_match")
        return "+".join(parts) if parts else "no_match"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["matched_dom_selectors"] = list(self.matched_dom_selectors)
        data["matched_text_phrases"] = list(self.matched_text_phrases)
        data["detected"] = self.detected
        data["reason"] = self.reason
        return data


def _url_signal(url: str) -> tuple[bool, str | None]:
    lower = url.lower()
    for pat in _CAPTCHA_URL_PATTERNS:
        if pat in lower:
            return True, pat
    return False, None


async def _dom_signal(page: Page) -> tuple[bool, tuple[str, ...]]:
    """Check the DOM for captcha/verify elements, return matched selectors."""
    try:
        matched = await page.evaluate("""() => {
            const selectors = [
                '[class*="captcha" i]',
                '[id*="captcha" i]',
                '[class*="verify" i]',
                '[id*="verify" i]',
                'iframe[src*="captcha" i]',
                'iframe[src*="challenge" i]',
                '[class*="slider" i][class*="verify" i]',
            ];
            const hits = [];
            for (const sel of selectors) {
                try {
                    if (document.querySelector(sel) !== null) hits.push(sel);
                } catch (e) { /* ignore bad selector */ }
            }
            return hits;
        }""")
    except Exception:
        logger.debug("DOM captcha signal eval failed", exc_info=True)
        return False, ()
    matched_tuple = tuple(matched or ())
    return bool(matched_tuple), matched_tuple


async def _text_signal(page: Page) -> tuple[bool, tuple[str, ...]]:
    """Check body text for anti-bot phrases, return matched phrases."""
    try:
        body_text = await page.evaluate("""() => {
            const t = (document.body && document.body.innerText) || '';
            return t.slice(0, 8000).toLowerCase();
        }""")
    except Exception:
        logger.debug("Text captcha signal eval failed", exc_info=True)
        return False, ()
    if not body_text:
        return False, ()
    hits = tuple(p for p in _CAPTCHA_TEXT_PATTERNS if p in body_text)
    return bool(hits), hits


async def detect_captcha(page: Page) -> CaptchaSignals:
    """Run all three captcha detection signals on the page.

    Returns a CaptchaSignals object. Check .detected to see if any fired.
    """
    url = ""
    try:
        url = page.url or ""
    except Exception:
        pass
    url_hit, url_pat = _url_signal(url)
    dom_hit, dom_matched = await _dom_signal(page)
    text_hit, text_matched = await _text_signal(page)
    return CaptchaSignals(
        url=url,
        url_match=url_hit,
        dom_match=dom_hit,
        text_match=text_hit,
        matched_url_pattern=url_pat,
        matched_dom_selectors=dom_matched,
        matched_text_phrases=text_matched,
    )


async def save_snapshot(
    page: Page,
    *,
    reason: str,
    signals: CaptchaSignals | None = None,
    job_id: str | None = None,
    set_number: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> Path | None:
    """Save a full page snapshot (screenshot + HTML + metadata) for analysis.

    Snapshots are stored under services/shopee/captcha_snapshots/ with a
    timestamp prefix so they sort chronologically.

    Returns the snapshot directory path, or None on failure.
    """
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        snap_dir = SNAPSHOT_DIR / ts
        snap_dir.mkdir(parents=True, exist_ok=True)

        try:
            await page.screenshot(
                path=str(snap_dir / "screenshot.png"), full_page=True
            )
        except Exception:
            logger.debug("Screenshot capture failed", exc_info=True)

        try:
            html = await page.content()
            (snap_dir / "page.html").write_text(html, encoding="utf-8")
        except Exception:
            logger.debug("HTML capture failed", exc_info=True)

        page_url = ""
        page_title = ""
        try:
            page_url = page.url or ""
        except Exception:
            pass
        try:
            page_title = await page.title()
        except Exception:
            pass

        meta: dict[str, Any] = {
            "url": page_url,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "reason": reason,
            "title": page_title,
            "job_id": job_id,
            "set_number": set_number,
            "signals": signals.to_dict() if signals else None,
        }
        if extra_meta:
            meta.update(extra_meta)
        (snap_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, default=str), encoding="utf-8"
        )
        logger.info("Captcha snapshot saved to %s (reason=%s)", snap_dir, reason)
        return snap_dir
    except Exception:
        logger.exception("Failed to save captcha snapshot")
        return None


def snapshot_relative_path(snap_dir: Path) -> str:
    """Return the snapshot path relative to SNAPSHOT_DIR for DB storage."""
    try:
        return str(snap_dir.relative_to(SNAPSHOT_DIR))
    except ValueError:
        return str(snap_dir)
