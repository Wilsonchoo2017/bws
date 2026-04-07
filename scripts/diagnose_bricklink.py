#!/usr/bin/env python3
"""Diagnostic probe for BrickLink silent ban detection.

Fetches a well-known item and analyzes the response to determine
whether BrickLink is serving normal data, degraded data, or empty shells.

Usage:
    python scripts/diagnose_bricklink.py [ITEM_ID]
    python scripts/diagnose_bricklink.py 10497-1
"""

import asyncio
import sys
import time

import httpx

from services.bricklink.parser import (
    build_item_url,
    build_price_guide_url,
    parse_full_item,
    parse_price_guide,
)
from services.http import get_browser_headers


# Well-known item with guaranteed pricing data
DEFAULT_ITEM = "10497-1"  # Galaxy Explorer

# Minimum content length for a real BrickLink page (bytes)
MIN_PAGE_BYTES = 2000

# Markers that indicate a real page vs shell/error
REAL_PAGE_MARKERS = [
    'bgcolor="#C0C0C0"',       # price guide table
    "Times Sold:",              # pricing data
    "catalogitem.page",         # navigation links
]

SHELL_PAGE_MARKERS = [
    "error.page",
    "Access Denied",
    "Please try again later",
    "captcha",
    "challenge-platform",     # AWS WAF active interstitial (not challenge.js)
    "awswaf-captcha",         # AWS WAF captcha
    "cloudflare",
]


def _headers() -> dict[str, str]:
    return get_browser_headers(
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        extra={
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        },
    )


async def probe_page(client: httpx.AsyncClient, url: str, label: str) -> dict:
    """Fetch a page and return diagnostic info."""
    start = time.monotonic()
    try:
        resp = await client.get(url, headers=_headers(), follow_redirects=True)
        elapsed_ms = (time.monotonic() - start) * 1000
    except Exception as e:
        return {"label": label, "error": str(e), "url": url}

    html = resp.text
    final_url = str(resp.url)

    # Check redirects
    redirect_chain = [str(r.url) for r in resp.history] if resp.history else []

    # Check for error page redirect
    is_error_redirect = "error.page" in final_url

    # Count real-page markers
    real_markers_found = [m for m in REAL_PAGE_MARKERS if m in html]
    shell_markers_found = [m for m in SHELL_PAGE_MARKERS if m.lower() in html.lower()]

    # Check content size
    content_len = len(html.encode("utf-8"))
    is_thin = content_len < MIN_PAGE_BYTES

    return {
        "label": label,
        "url": url,
        "final_url": final_url,
        "status": resp.status_code,
        "content_bytes": content_len,
        "elapsed_ms": round(elapsed_ms),
        "redirect_chain": redirect_chain,
        "is_error_redirect": is_error_redirect,
        "real_markers": real_markers_found,
        "shell_markers": shell_markers_found,
        "is_thin_page": is_thin,
    }


def diagnose(results: list[dict]) -> str:
    """Analyze probe results and return diagnosis."""
    issues = []

    for r in results:
        if "error" in r:
            issues.append(f"  NETWORK ERROR on {r['label']}: {r['error']}")
            continue

        if r["is_error_redirect"]:
            code = ""
            if "code=429" in r["final_url"]:
                code = " (429 rate limit)"
            elif "code=403" in r["final_url"]:
                code = " (403 IP ban)"
            issues.append(f"  EXPLICIT BAN{code} on {r['label']}: redirected to {r['final_url']}")
            continue

        if r["is_thin_page"]:
            issues.append(
                f"  THIN PAGE on {r['label']}: only {r['content_bytes']} bytes "
                f"(expected >{MIN_PAGE_BYTES})"
            )

        if r["shell_markers"]:
            issues.append(
                f"  SHELL/BLOCK MARKERS on {r['label']}: {r['shell_markers']}"
            )

        if not r["real_markers"]:
            issues.append(
                f"  NO REAL MARKERS on {r['label']}: page looks empty/degraded "
                f"({r['content_bytes']} bytes)"
            )

    if not issues:
        return "HEALTHY: BrickLink is serving normal data."

    return "ISSUES DETECTED:\n" + "\n".join(issues)


async def main(item_id: str) -> None:
    print(f"Probing BrickLink for item {item_id}...\n")

    item_url = build_item_url("S", item_id)
    price_url = build_price_guide_url("S", item_id)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Probe both pages
        results = []
        r1 = await probe_page(client, item_url, "catalog")
        results.append(r1)

        # Small delay between requests
        await asyncio.sleep(3)

        r2 = await probe_page(client, price_url, "price_guide")
        results.append(r2)

    # Print raw diagnostics
    for r in results:
        print(f"--- {r['label'].upper()} ---")
        if "error" in r:
            print(f"  Error: {r['error']}")
            continue
        print(f"  URL:            {r['url']}")
        print(f"  Final URL:      {r['final_url']}")
        print(f"  Status:         {r['status']}")
        print(f"  Content bytes:  {r['content_bytes']}")
        print(f"  Elapsed:        {r['elapsed_ms']}ms")
        if r["redirect_chain"]:
            print(f"  Redirects:      {r['redirect_chain']}")
        print(f"  Real markers:   {r['real_markers']}")
        print(f"  Shell markers:  {r['shell_markers']}")
        print(f"  Thin page:      {r['is_thin_page']}")
        print()

    # Try parsing if we got HTML
    price_result = next((r for r in results if r["label"] == "price_guide"), None)
    if price_result and "error" not in price_result and not price_result["is_error_redirect"]:
        print("--- PARSE ATTEMPT ---")
        # Re-fetch for parsing (we don't store the HTML in diagnostics for memory)
        async with httpx.AsyncClient(timeout=30.0) as client:
            await asyncio.sleep(3)
            resp = await client.get(price_url, headers=_headers(), follow_redirects=True)
            html = resp.text
            try:
                pricing = parse_price_guide(html)
                has_data = any(v is not None for v in pricing.values())
                print(f"  Parse success: {has_data}")
                for k, v in pricing.items():
                    if v is not None:
                        print(f"    {k}: avg={v.avg_price}, times_sold={v.times_sold}")
                    else:
                        print(f"    {k}: None")
                if not has_data:
                    print("  WARNING: All pricing boxes are None -- possible silent ban")
            except ValueError as e:
                print(f"  Parse error: {e}")
                print("  This could indicate silent ban (empty page structure)")

    print()
    print("=== DIAGNOSIS ===")
    print(diagnose(results))


if __name__ == "__main__":
    item_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ITEM
    asyncio.run(main(item_id))
