"""Image downloader -- fetches BrickLink images to local storage."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from config.settings import (
    BWS_IMAGES_PATH,
    BWS_IMAGES_MINIFIGS_PATH,
    BWS_IMAGES_PARTS_PATH,
    BWS_IMAGES_SETS_PATH,
    get_random_accept_language,
    get_random_delay,
    get_random_user_agent,
)
from services.images.repository import (
    get_pending_assets,
    mark_downloaded,
    mark_failed,
)

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

logger = logging.getLogger("bws.images")

# Lighter rate limiting for CDN image downloads (static assets)
_IMAGE_MIN_DELAY_MS = 500
_IMAGE_MAX_DELAY_MS = 1500


def _ensure_directories() -> None:
    """Create image storage directories if they don't exist."""
    for path in (BWS_IMAGES_PATH, BWS_IMAGES_SETS_PATH, BWS_IMAGES_MINIFIGS_PATH, BWS_IMAGES_PARTS_PATH):
        path.mkdir(parents=True, exist_ok=True)


def _image_headers() -> dict[str, str]:
    """Generate browser-like headers for image downloads."""
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
        "Accept-Language": get_random_accept_language(),
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.bricklink.com/",
        "Connection": "keep-alive",
    }


def resolve_local_path(asset_type: str, item_id: str) -> str:
    """Return relative path for an asset, e.g. 'sets/75192-1.png'."""
    type_dirs = {"set": "sets", "minifig": "minifigs", "part": "parts"}
    directory = type_dirs.get(asset_type, asset_type)
    return f"{directory}/{item_id}.png"


def get_absolute_path(relative_path: str) -> Path:
    """Return full filesystem path for a relative image path."""
    return BWS_IMAGES_PATH / relative_path


async def download_single(
    client: httpx.AsyncClient,
    source_url: str,
    local_path: str,
) -> tuple[bool, int | None, str | None]:
    """Download a single image.

    Returns (success, file_size_bytes, error_message).
    """
    dest = get_absolute_path(local_path)
    try:
        response = await client.get(source_url, headers=_image_headers(), follow_redirects=True)
        if response.status_code == 404:
            return False, None, "404 Not Found"
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            return False, None, f"Not an image: {content_type}"

        data = response.content
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True, len(data), None

    except httpx.HTTPStatusError as exc:
        return False, None, f"HTTP {exc.response.status_code}"
    except httpx.RequestError as exc:
        return False, None, str(exc)


async def download_batch(
    conn: "DuckDBPyConnection",
    *,
    batch_size: int = 50,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    """Download a batch of pending images.

    Returns (downloaded_count, failed_count).
    """
    _ensure_directories()
    pending = get_pending_assets(conn, limit=batch_size)
    if not pending:
        return 0, 0

    logger.info("Image download batch: %d assets to process", len(pending))
    downloaded = 0
    failed = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, asset in enumerate(pending):
            source_url = asset["source_url"]
            local_path = asset["local_path"]
            asset_type = asset["asset_type"]
            item_id = asset["item_id"]

            success, file_size, error = await download_single(client, source_url, local_path)

            if success:
                content_type = "image/png"
                if local_path.endswith(".jpg") or local_path.endswith(".jpeg"):
                    content_type = "image/jpeg"
                mark_downloaded(conn, asset_type, item_id, file_size, content_type)
                downloaded += 1
                logger.debug("Downloaded %s/%s (%d bytes)", asset_type, item_id, file_size)
            else:
                mark_failed(conn, asset_type, item_id, error or "Unknown error")
                failed += 1
                logger.warning("Failed %s/%s: %s", asset_type, item_id, error)

            if on_progress:
                on_progress(i + 1, len(pending))

            # Rate limit between downloads
            delay = get_random_delay(min_ms=_IMAGE_MIN_DELAY_MS, max_ms=_IMAGE_MAX_DELAY_MS)
            await asyncio.sleep(delay)

    logger.info("Image batch complete: %d downloaded, %d failed", downloaded, failed)
    return downloaded, failed
