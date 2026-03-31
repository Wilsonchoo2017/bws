"""Image assets API routes -- serve local images, trigger downloads."""

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse

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
async def image_stats():
    """Get image download statistics."""
    conn = get_connection()
    init_schema(conn)
    stats = get_download_stats(conn)
    conn.close()
    return stats


@router.get("/{asset_type}/{item_id}")
async def serve_image(asset_type: str, item_id: str):
    """Serve a locally downloaded image, or redirect to CDN if not yet downloaded."""
    conn = get_connection()
    init_schema(conn)
    asset = get_asset(conn, asset_type, item_id)
    conn.close()

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


@router.post("/download")
async def trigger_download(background_tasks: BackgroundTasks, batch_size: int = 50):
    """Trigger a batch image download in the background."""
    conn = get_connection()
    init_schema(conn)

    # Register any unregistered existing items first
    registered = register_existing_images(conn)

    async def _run_batch() -> None:
        dl_conn = get_connection()
        init_schema(dl_conn)
        await download_batch(dl_conn, batch_size=batch_size)
        dl_conn.close()

    background_tasks.add_task(_run_batch)

    stats = get_download_stats(conn)
    conn.close()
    return {
        "message": f"Download triggered. {registered} new assets registered.",
        "stats": stats,
    }
