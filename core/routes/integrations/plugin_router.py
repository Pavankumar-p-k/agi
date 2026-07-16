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
# api/plugin_routes.py
# REST API for plugin management.
# Register in your main app:
#   from api.plugin_routes import router as plugin_router
#   app.include_router(plugin_router)

import subprocess
import sys
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.plugins import get_plugin_loader, get_plugin_registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class SettingsPatch(BaseModel):
    settings: dict[str, Any]

class InstallRequest(BaseModel):
    package_name: str


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #

@router.get("/search")
async def search_plugins(q: str):
    """Search PyPI for JARVIS plugins (Mock for now)."""
    # In production, this would query PyPI JSON API for packages starting with 'jarvis-plugin-'
    return {
        "results": [
            {"name": f"jarvis-plugin-{q}", "description": f"AI-powered {q} enhancement for JARVIS", "version": "0.1.0"},
            {"name": "jarvis-plugin-sample", "description": "A sample plugin for testing", "version": "1.0.2"}
        ]
    }


@router.post("/install")
async def install_plugin(req: InstallRequest):
    """Pip install a plugin package."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", req.package_name])
        return {"status": "success", "package": req.package_name}
    except Exception:
        raise HTTPException(status_code=500, detail="Request failed. Please try again.")


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str):
    """Get manifest + current settings for a plugin."""
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {
        "manifest": manifest.to_dict(),
        "settings": registry.get_settings(plugin_id),
    }


@router.post("/{plugin_id}/enable")
async def enable_plugin(plugin_id: str):
    registry = get_plugin_registry()
    if not registry.enable(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {"status": "enabled", "id": plugin_id}


@router.post("/{plugin_id}/disable")
async def disable_plugin(plugin_id: str):
    registry = get_plugin_registry()
    if not registry.disable(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {"status": "disabled", "id": plugin_id}


@router.post("/{plugin_id}/toggle")
async def toggle_plugin(plugin_id: str):
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    # manifest is a PluginManifest object — check if it has an 'enabled' property
    enabled = getattr(manifest, 'enabled', False)
    if enabled:
        if not registry.disable(plugin_id):
            raise HTTPException(status_code=500, detail=f"Failed to disable plugin '{plugin_id}'")
        return {"status": "disabled", "enabled": False, "id": plugin_id}
    else:
        if not registry.enable(plugin_id):
            raise HTTPException(status_code=500, detail=f"Failed to enable plugin '{plugin_id}'")
        return {"status": "enabled", "enabled": True, "id": plugin_id}


@router.post("/{plugin_id}/reload")
async def reload_plugin(plugin_id: str):
    loader = get_plugin_loader()
    ok = loader.reload(plugin_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found or reload failed")
    return {"status": "reloaded", "id": plugin_id}


@router.get("/{plugin_id}/settings")
async def get_plugin_settings(plugin_id: str):
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return {"settings": registry.get_settings(plugin_id)}


@router.patch("/{plugin_id}/settings")
async def update_plugin_settings(plugin_id: str, body: SettingsPatch):
    registry = get_plugin_registry()
    ok = registry.update_settings(plugin_id, body.settings)
    if not ok:
        raise HTTPException(status_code=400, detail="Settings update failed — validation error or unknown plugin")
    return {"status": "updated", "id": plugin_id}
