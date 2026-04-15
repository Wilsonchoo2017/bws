"""Tests for multi-signal Shopee captcha detection."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.shopee.captcha_detection import (
    CaptchaSignals,
    _url_signal,
    detect_captcha,
)


class TestUrlSignal:
    def test_captcha_url_matches(self):
        hit, pat = _url_signal("https://shopee.com.my/verify/traffic")
        assert hit is True
        assert pat == "/verify/"

    def test_security_check_url_matches(self):
        hit, pat = _url_signal(
            "https://shopee.com.my/security-check?token=abc"
        )
        assert hit is True
        assert pat == "security-check"

    def test_normal_url_does_not_match(self):
        hit, pat = _url_signal("https://shopee.com.my/legoshopmy")
        assert hit is False
        assert pat is None


def _fake_page(*, url: str, dom_hits: list[str], body_text: str) -> MagicMock:
    page = MagicMock()
    page.url = url

    async def _eval(script: str):
        if "selectors" in script or "captcha" in script.lower():
            return dom_hits
        if "innerText" in script:
            return body_text.lower()
        return None

    page.evaluate = AsyncMock(side_effect=_eval)
    return page


class TestDetectCaptcha:
    def test_url_only_signal(self):
        page = _fake_page(
            url="https://shopee.com.my/verify/traffic",
            dom_hits=[],
            body_text="normal page body",
        )
        signals = asyncio.run(detect_captcha(page))
        assert signals.detected is True
        assert signals.url_match is True
        assert signals.dom_match is False
        assert signals.text_match is False
        assert signals.reason == "url_match"

    def test_dom_only_signal(self):
        page = _fake_page(
            url="https://shopee.com.my/legoshopmy",
            dom_hits=['[class*="captcha" i]'],
            body_text="LEGO official shop",
        )
        signals = asyncio.run(detect_captcha(page))
        assert signals.detected is True
        assert signals.dom_match is True
        assert signals.matched_dom_selectors == ('[class*="captcha" i]',)
        assert signals.reason == "dom_match"

    def test_text_only_signal(self):
        page = _fake_page(
            url="https://shopee.com.my/legoshopmy",
            dom_hits=[],
            body_text="Please verify it's you before continuing",
        )
        signals = asyncio.run(detect_captcha(page))
        assert signals.detected is True
        assert signals.text_match is True
        assert "verify it's you" in signals.matched_text_phrases

    def test_no_signals_fires(self):
        page = _fake_page(
            url="https://shopee.com.my/legoshopmy",
            dom_hits=[],
            body_text="LEGO Star Wars Millennium Falcon — RM 2,999",
        )
        signals = asyncio.run(detect_captcha(page))
        assert signals.detected is False
        assert signals.reason == "no_match"

    def test_multiple_signals_joined(self):
        page = _fake_page(
            url="https://shopee.com.my/verify/traffic",
            dom_hits=['[id*="verify" i]'],
            body_text="Security verification required",
        )
        signals = asyncio.run(detect_captcha(page))
        assert signals.detected is True
        assert signals.url_match is True
        assert signals.dom_match is True
        assert signals.text_match is True
        assert "url_match" in signals.reason
        assert "dom_match" in signals.reason
        assert "text_match" in signals.reason


class TestCaptchaSignalsSerialization:
    def test_to_dict_shape(self):
        signals = CaptchaSignals(
            url="https://shopee.com.my/verify/x",
            url_match=True,
            dom_match=False,
            text_match=True,
            matched_url_pattern="/verify/",
            matched_text_phrases=("verify it's you",),
        )
        data = signals.to_dict()
        assert data["detected"] is True
        assert data["reason"] == "url_match+text_match"
        assert data["matched_text_phrases"] == ["verify it's you"]
        assert data["matched_dom_selectors"] == []
