# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from core.settings.store import get_settings_store

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
    except KeyError:
        raise HTTPException(status_code=404, detail="Setting not found")

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
    except KeyError:
        raise HTTPException(status_code=404, detail="Setting not found")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception:
        raise HTTPException(status_code=500, detail="Request failed. Please try again.")

@router.post("/reset")
async def reset_settings(payload: dict | None = Body(None)):
    """Reset settings to defaults."""
    key = payload.get("key") if payload else None
    try:
        store.reset(key)
        return {"status": "success", "message": f"Reset {'all settings' if not key else key} to default"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Setting not found")

@router.get("/export")
async def export_settings():
    """Export full settings (unmasked for download/backup purposes)."""
    # Note: In a real production app, this should be protected by stronger auth
    # and maybe even then it should return a file.
    return store._settings.model_dump()
