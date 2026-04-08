"""Listing title, description, and data helpers.

Python equivalent of frontend listing-template.ts. Generates
marketplace-optimized text and collects image file paths.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import asyncio
import logging

import httpx

_IMAGES_BASE = Path.home() / ".bws" / "images"

logger = logging.getLogger("bws.listing.templates")


def generate_listing_title(item: dict[str, Any]) -> str:
    """Generate a marketplace-optimized listing title.

    Format: LEGO NINJAGO 71841 Dragonian Storm Village (260pcs, 7 Minifigures) MISB NEW SEALED
    """
    parts: list[str] = ["LEGO"]

    if item.get("theme"):
        parts.append(item["theme"])

    parts.append(item["set_number"])

    if item.get("title"):
        parts.append(item["title"])

    extras: list[str] = []
    if item.get("parts_count"):
        extras.append(f"{item['parts_count']}pcs")
    if item.get("minifig_count"):
        extras.append(f"{item['minifig_count']} Minifigures")
    if extras:
        parts.append(f"({', '.join(extras)})")

    parts.append("MISB NEW SEALED")

    if item.get("year_retired"):
        parts.append("RETIRED")

    return " ".join(parts)


def generate_listing_description(
    item: dict[str, Any],
    minifigures: list[dict[str, Any]],
) -> str:
    """Generate a marketplace listing description."""
    lines: list[str] = []

    # Keywords up top
    lines.append("100% Genuine LEGO Product")
    lines.append("Brand New | Factory Sealed | MISB")
    lines.append("Ready Stock")
    lines.append("Not for fussy buyers or box collectors.")
    lines.append("")

    # Specs
    theme = item.get("theme")
    if theme:
        lines.append(f"Theme: {theme}")
    if item.get("parts_count"):
        lines.append(f"Pieces: {item['parts_count']:,}")

    # Minifigures
    minifig_count = item.get("minifig_count")
    if minifig_count and minifigures:
        names = ", ".join(
            mf["name"] for mf in minifigures if mf.get("name")
        )
        lines.append(f"Minifigures: {minifig_count} ({names})")
    elif minifig_count:
        lines.append(f"Minifigures: {minifig_count}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shipping adjustments
# ---------------------------------------------------------------------------

_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)"
)


def _parse_weight_kg(weight: str | None) -> float | None:
    if not weight:
        return None
    trimmed = weight.strip().lower()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*kg$", trimmed)
    if m:
        return float(m.group(1))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*g$", trimmed)
    if m:
        return float(m.group(1)) / 1000
    return None


def shipping_weight_kg(weight_str: str | None) -> float | None:
    """Parse weight string and add 20% buffer for packaging."""
    kg = _parse_weight_kg(weight_str)
    if kg is None:
        return None
    return round(kg * 1.2, 2)


def shipping_dimensions_cm(
    dim_str: str | None,
) -> tuple[int, int, int] | None:
    """Parse dimensions string, add 5cm to each, return as integers.

    Shopee's Parcel Size fields expect integer centimeters.
    Returns (width, length, height) -- Shopee's W x L x H order.
    """
    if not dim_str:
        return None
    m = _DIM_RE.search(dim_str)
    if not m:
        return None
    l_cm = round(float(m.group(1)) + 5)
    w_cm = round(float(m.group(2)) + 5)
    h_cm = round(float(m.group(3)) + 5)
    # Shopee form order: W x L x H
    return (w_cm, l_cm, h_cm)


# ---------------------------------------------------------------------------
# Image path collection
# ---------------------------------------------------------------------------


def _download_pending_images(conn: Any, set_number: str) -> None:
    """Download any pending images for this set and its minifigs on-demand."""
    variants = _set_number_variants(set_number)

    # Collect all pending assets for this set + its minifigs
    pending: list[tuple[str, str, str, str]] = []  # (asset_type, item_id, source_url, local_path)

    for variant in variants:
        rows = conn.execute(
            "SELECT asset_type, item_id, source_url, local_path "
            "FROM image_assets WHERE asset_type = 'set' AND item_id = ? "
            "AND status != 'downloaded'",
            [variant],
        ).fetchall()
        pending.extend(rows)

        mf_rows = conn.execute(
            """
            SELECT ia.asset_type, ia.item_id, ia.source_url, ia.local_path
            FROM set_minifigures sm
            JOIN image_assets ia
                ON ia.asset_type = 'minifig'
                AND ia.item_id = sm.minifig_id
                AND ia.status != 'downloaded'
            WHERE sm.set_item_id = ?
            """,
            [variant],
        ).fetchall()
        pending.extend(mf_rows)
        if mf_rows:
            break

    if not pending:
        return

    logger.info("Downloading %d pending images for listing %s", len(pending), set_number)

    async def _download_all() -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            for asset_type, item_id, source_url, local_path in pending:
                dest = _IMAGES_BASE / local_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    resp = await client.get(
                        source_url,
                        headers={"User-Agent": "Mozilla/5.0"},
                        follow_redirects=True,
                    )
                    if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                        dest.write_bytes(resp.content)
                        conn.execute(
                            "UPDATE image_assets SET status = 'downloaded', "
                            "file_size_bytes = ?, downloaded_at = now() "
                            "WHERE asset_type = ? AND item_id = ?",
                            [len(resp.content), asset_type, item_id],
                        )
                        logger.info("Downloaded %s/%s -> %s", asset_type, item_id, local_path)
                    else:
                        logger.warning("Failed to download %s: HTTP %d", source_url, resp.status_code)
                except Exception as exc:
                    logger.warning("Download error for %s: %s", source_url, exc)

    try:
        asyncio.run(_download_all())
    except RuntimeError:
        # Already in an async context -- use a new loop in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_download_all())).result(timeout=60)


def _set_number_variants(set_number: str) -> list[str]:
    """Return set_number with and without -1 suffix for DB lookups."""
    if "-" in set_number:
        return [set_number, set_number.split("-")[0]]
    return [set_number, f"{set_number}-1"]


def collect_image_paths(
    conn: Any,
    set_number: str,
    max_photos: int = 9,
) -> list[Path]:
    """Collect downloaded image file paths for a set and its minifigures.

    Returns absolute paths, set image first, then minifig images, capped
    at ``max_photos``. Handles both '71841' and '71841-1' formats.
    """
    # Download any pending images first
    _download_pending_images(conn, set_number)

    paths: list[Path] = []
    variants = _set_number_variants(set_number)

    # Set image -- try each variant
    for variant in variants:
        row = conn.execute(
            "SELECT local_path FROM image_assets "
            "WHERE asset_type = 'set' AND item_id = ?",
            [variant],
        ).fetchone()
        if row and row[0]:
            p = _IMAGES_BASE / row[0]
            if p.exists():
                paths.append(p)
                break

    # Minifig images -- try each variant for set_item_id
    for variant in variants:
        mf_rows = conn.execute(
            """
            SELECT ia.local_path, sm.minifig_id
            FROM set_minifigures sm
            JOIN image_assets ia
                ON ia.asset_type = 'minifig'
                AND ia.item_id = sm.minifig_id
            WHERE sm.set_item_id = ?
            GROUP BY ia.local_path, sm.minifig_id
            ORDER BY sm.minifig_id
            """,
            [variant],
        ).fetchall()
        if mf_rows:
            for mf_row in mf_rows:
                if mf_row[0]:
                    p = _IMAGES_BASE / mf_row[0]
                    if p.exists():
                        paths.append(p)
            break

    return paths[:max_photos]
