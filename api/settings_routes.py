from fastapi import APIRouter, HTTPException, Body
from typing import Any, Optional
from core.settings.store import get_settings_store
from pydantic import ValidationError

router = APIRouter(prefix="/settings", tags=["Settings"])
store = get_settings_store()

@router.get("")
async def get_all_settings():
    """Return all settings (masked)."""
    return store.export()

@router.get("/{key}")
async def get_setting(key: str):
    """Return a specific setting value."""
    try:
        return {"key": key, "value": store.get(key)}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.patch("/{key}")
async def update_setting(key: str, payload: dict = Body(...)):
    """Update a specific setting."""
    if "value" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'value' in request body")
    
    try:
        if store.set(key, payload["value"]):
            return {"status": "success", "key": key, "new_value": payload["value"]}
        else:
            raise HTTPException(status_code=500, detail="Failed to save setting")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_settings(payload: Optional[dict] = Body(None)):
    """Reset settings to defaults."""
    key = payload.get("key") if payload else None
    try:
        store.reset(key)
        return {"status": "success", "message": f"Reset {'all settings' if not key else key} to default"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/export")
async def export_settings():
    """Export full settings (unmasked for download/backup purposes)."""
    # Note: In a real production app, this should be protected by stronger auth
    # and maybe even then it should return a file.
    return store._settings.model_dump()
