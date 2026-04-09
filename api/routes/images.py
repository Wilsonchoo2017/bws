"""Image assets API routes -- serve local images, trigger downloads."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse

from api.dependencies import get_db
from db.connection import get_connection
from db.schema import init_schema
from services.images.downloader import download_batch, get_absolute_path
from services.images.repository import (
    get_asset,
    get_download_stats,
    register_existing_images,
)


router = APIRouter(prefix="/images", tags=["images"])


@router.get("/stats")
async def image_stats(conn: Any = Depends(get_db)):
    """Get image download statistics."""
    return get_download_stats(conn)


@router.get("/{asset_type}/{item_id}")
async def serve_image(asset_type: str, item_id: str, conn: Any = Depends(get_db)):
    """Serve a locally downloaded image, or redirect to CDN if not yet downloaded."""
    asset = get_asset(conn, asset_type, item_id)

    if asset and asset["status"] == "downloaded":
        file_path = get_absolute_path(asset["local_path"])
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                media_type=asset.get("content_type", "image/png"),
                headers={"Cache-Control": "public, max-age=86400"},
            )

    # Fallback: redirect to original source URL
    if asset and asset.get("source_url"):
        return RedirectResponse(url=asset["source_url"], status_code=302)

    # Not registered at all -- construct BrickLink fallback
    fallback_urls = {
        "set": f"https://img.bricklink.com/ItemImage/SN/0/{item_id}.png",
        "minifig": f"https://img.bricklink.com/ItemImage/MN/0/{item_id}.png",
        "part": f"https://img.bricklink.com/ItemImage/PN/0/{item_id}.png",
    }
    fallback = fallback_urls.get(asset_type)
    if fallback:
        return RedirectResponse(url=fallback, status_code=302)

    return JSONResponse(status_code=404, content={"error": "Image not found"})


@router.get("/keepa/{set_number}")
async def serve_keepa_chart(set_number: str):
    """Serve the Keepa chart screenshot for a set."""
    from pathlib import Path

    from config.settings import BWS_IMAGES_PATH

    screenshot_dir = BWS_IMAGES_PATH / "keepa"
    # Find any matching screenshot
    for path in sorted(screenshot_dir.glob(f"{set_number}_*.png"), reverse=True):
        if path.exists():
            return FileResponse(
                path=str(path),
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )

    return JSONResponse(
        status_code=404,
        content={"detail": "Keepa chart screenshot not found"},
    )


@router.post("/open/{set_number}")
async def open_in_finder(set_number: str):
    """Open all listing images for a set in Finder (macOS).

    Collects the same images that would be used in a listing,
    then reveals them in Finder via 'open -R'.
    """
    import subprocess
    from pathlib import Path

    from services.listing.templates import collect_image_paths

    conn = get_connection()
    paths = collect_image_paths(conn, set_number, max_photos=10, brand_border=False)
    conn.close()

    if not paths:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No images found for {set_number}"},
        )

    # Reveal the first image in Finder (selects it, shows the folder)
    first = paths[0]
    subprocess.Popen(["open", "-R", str(first)])

    return {
        "message": f"Opened {len(paths)} images in Finder",
        "images": [str(p) for p in paths],
    }


@router.post("/download")
async def trigger_download(
    background_tasks: BackgroundTasks,
    batch_size: int = 50,
    conn: Any = Depends(get_db),
):
    """Trigger a batch image download in the background."""
    # Register any unregistered existing items first
    registered = register_existing_images(conn)

    async def _run_batch() -> None:
        dl_conn = get_connection()
        init_schema(dl_conn)
        await download_batch(dl_conn, batch_size=batch_size)
        dl_conn.close()

    background_tasks.add_task(_run_batch)

    stats = get_download_stats(conn)
    return {
        "message": f"Download triggered. {registered} new assets registered.",
        "stats": stats,
    }
