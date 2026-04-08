"""Runtime settings API -- read and update operational settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.runtime_settings import runtime_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SectionUpdate(BaseModel):
    """Payload for updating a single settings section."""

    values: dict | list[Any]


@router.get("")
async def get_settings() -> dict:
    """Return all current runtime settings."""
    return {
        "success": True,
        "data": runtime_settings.get_all(),
        "defaults": runtime_settings.get_defaults(),
    }


@router.put("/{section}")
async def update_section(section: str, body: SectionUpdate) -> dict:
    """Update a single settings section and apply changes at runtime."""
    try:
        runtime_settings.update_section(section, body.values)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "data": runtime_settings.get_section(section),
    }


@router.post("/reset")
async def reset_defaults() -> dict:
    """Reset all settings to factory defaults."""
    defaults = runtime_settings.get_defaults()
    for section in defaults:
        runtime_settings.update_section(section, defaults[section])
    return {
        "success": True,
        "data": runtime_settings.get_all(),
    }


@router.post("/reset/{section}")
async def reset_section_defaults(section: str) -> dict:
    """Reset a single section to factory defaults."""
    defaults = runtime_settings.get_defaults()
    if section not in defaults:
        raise HTTPException(status_code=404, detail=f"Unknown section: {section}")
    runtime_settings.update_section(section, defaults[section])
    return {
        "success": True,
        "data": runtime_settings.get_section(section),
    }
