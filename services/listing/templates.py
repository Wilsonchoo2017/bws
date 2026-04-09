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
from PIL import Image

_IMAGES_BASE = Path.home() / ".bws" / "images"
_PROCESSED_DIR = _IMAGES_BASE / "processed"
_HIRES_DIR = _IMAGES_BASE / "hires"

BRAND_COLOR = (149, 22, 12)  # Brickwerk dark red (#95160c)
BORDER_RATIO = 0.06  # Border width as fraction of shorter dimension

logger = logging.getLogger("bws.listing.templates")


def _add_brand_border(src: Path) -> Path:
    """Add a brand-colored border to an image on a white background.

    Steps:
    1. Place the source image (which may have transparency) on a white canvas
    2. Draw the brand-colored border outline on top

    The output keeps the same dimensions as the source. The original file
    is never modified; bordered copies are cached in ``_PROCESSED_DIR``.
    """
    _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = _PROCESSED_DIR / f"bordered_{src.name}"

    # Re-use cached version if it's newer than the source
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest

    img = Image.open(src)
    w, h = img.size
    border = max(int(min(w, h) * BORDER_RATIO), 2)

    # White background first, then composite the image on top
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    if img.mode == "RGBA":
        canvas.paste(img, (0, 0), img)
    else:
        canvas.paste(img.convert("RGB"), (0, 0))

    # Draw brand border outline
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    for i in range(border):
        draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=BRAND_COLOR)
    canvas.save(dest, format="PNG")
    logger.info("Created bordered image %s (%dx%d, border=%dpx)", dest.name, w, h, border)
    return dest


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
    *,
    platform: str = "shopee",
) -> str:
    """Generate a marketplace listing description.

    Args:
        item: Item detail dict from database.
        minifigures: List of minifigure dicts.
        platform: Target marketplace ("shopee", "carousell", "facebook").
    """
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

    # Platform-specific additions
    if platform == "carousell":
        from config.settings import CAROUSELL_CONFIG
        lines.append("")
        lines.append(CAROUSELL_CONFIG.postage_fee_note)
        lines.append(CAROUSELL_CONFIG.meetup_note)
    elif platform == "facebook":
        from config.settings import CAROUSELL_CONFIG
        lines.append("")
        lines.append(CAROUSELL_CONFIG.postage_fee_note)
        lines.append(CAROUSELL_CONFIG.meetup_note)

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


def _fetch_gallery_urls(set_number: str) -> list[str]:
    """Fetch the full BrickLink gallery image URLs for a set.

    Scrapes the catalog page and extracts hi-res URLs in order:
    SN (box) -> ON (alternate) -> EXTN (additional user images).
    """
    from services.bricklink.parser import extract_gallery_image_urls

    variant = set_number if "-" in set_number else f"{set_number}-1"
    url = f"https://www.bricklink.com/v2/catalog/catalogitem.page?S={variant}"

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
            timeout=30,
        )
        if resp.status_code == 200:
            return extract_gallery_image_urls(resp.text)
    except Exception as exc:
        logger.warning("Failed to fetch gallery for %s: %s", set_number, exc)

    return []


_BE_HTML_DIR = Path("logs/brickeconomy_snapshots")


def _fetch_be_gallery_urls(set_number: str) -> list[str]:
    """Extract product gallery image URLs from saved BrickEconomy snapshots.

    BE blocks direct HTTP requests (Cloudflare), so we read from HTML
    snapshots saved by the BE scraper. The image CDN itself allows
    direct downloads. Typically returns 5-6 images per set.
    """
    from services.brickeconomy.parser import extract_gallery_image_urls

    bare = set_number.split("-")[0]

    # Find the most recent snapshot for this set
    if not _BE_HTML_DIR.exists():
        return []

    matches = sorted(_BE_HTML_DIR.glob(f"*_{bare}.html"), reverse=True)
    if not matches:
        return []

    try:
        html = matches[0].read_text()
        urls = extract_gallery_image_urls(html)
        if urls:
            logger.info(
                "BrickEconomy gallery for %s: %d images (from %s)",
                set_number, len(urls), matches[0].name,
            )
        return urls
    except Exception as exc:
        logger.warning("Failed to parse BE snapshot for %s: %s", set_number, exc)

    return []


def _download_gallery_images(
    set_number: str, gallery_urls: list[str], max_photos: int,
) -> list[Path]:
    """Download gallery images to hires/ cache, return local paths."""
    _HIRES_DIR.mkdir(parents=True, exist_ok=True)
    targets: list[tuple[str, Path]] = []

    for i, url in enumerate(gallery_urls[:max_photos]):
        # Name: {set_number}_0.png, {set_number}_1.png, ...
        dest = _HIRES_DIR / f"{set_number}_{i}.png"
        targets.append((url, dest))

    # Filter to only those not yet cached
    to_download = [(url, dest) for url, dest in targets if not (dest.exists() and dest.stat().st_size > 10_000)]

    if to_download:
        logger.info("Downloading %d gallery images for %s", len(to_download), set_number)

        async def _fetch_all() -> None:
            async with httpx.AsyncClient(timeout=30) as client:
                for url, dest in to_download:
                    try:
                        resp = await client.get(
                            url,
                            headers={"User-Agent": "Mozilla/5.0"},
                            follow_redirects=True,
                        )
                        if resp.status_code == 200 and resp.headers.get(
                            "content-type", ""
                        ).startswith("image/"):
                            dest.write_bytes(resp.content)
                            logger.info("Downloaded %s (%d bytes)", dest.name, len(resp.content))
                        else:
                            logger.warning("Gallery download failed %s: HTTP %d", url, resp.status_code)
                    except Exception as exc:
                        logger.warning("Gallery download error %s: %s", url, exc)

        try:
            asyncio.run(_fetch_all())
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(lambda: asyncio.run(_fetch_all())).result(timeout=120)

    return [dest for _, dest in targets if dest.exists() and dest.stat().st_size > 10_000]


def collect_image_paths(
    conn: Any,
    set_number: str,
    max_photos: int = 9,
    brand_border: bool = True,
) -> list[Path]:
    """Collect all hi-res set images from BrickLink gallery for a listing.

    Fetches the full image gallery (box, alternate, additional images)
    in BrickLink display order. Images are cached in hires/ so subsequent
    listings reuse them. Handles both '71841' and '71841-1' formats.
    """
    variant = set_number if "-" in set_number else f"{set_number}-1"

    # Check if gallery is already cached
    cached = sorted(_HIRES_DIR.glob(f"{variant}_*.png")) if _HIRES_DIR.exists() else []
    cached = [p for p in cached if p.stat().st_size > 10_000]

    if not cached:
        gallery_urls = _fetch_gallery_urls(variant)
        if gallery_urls:
            cached = _download_gallery_images(variant, gallery_urls, max_photos)

    # Supplement with BrickEconomy gallery if BrickLink has fewer than max
    if len(cached) < max_photos:
        be_urls = _fetch_be_gallery_urls(variant)
        if be_urls:
            be_paths = _download_gallery_images(
                f"{variant}_be", be_urls, max_photos - len(cached),
            )
            cached.extend(be_paths)

    # Fallback: use the single image from image_assets if all else fails
    if not cached:
        _download_pending_images(conn, set_number)
        for v in _set_number_variants(set_number):
            row = conn.execute(
                "SELECT local_path FROM image_assets "
                "WHERE asset_type = 'set' AND item_id = ?",
                [v],
            ).fetchone()
            if row and row[0]:
                p = _IMAGES_BASE / row[0]
                if p.exists():
                    cached = [p]
                    break

    paths = cached[:max_photos]

    # Add brand border to the first (set) image
    if paths and brand_border:
        paths = [_add_brand_border(paths[0]), *paths[1:]]

    return paths
