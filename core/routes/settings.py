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
"""
core/routes/settings.py — Settings REST API.

Mount in your FastAPI app:
    from core.routes.settings import router as settings_router
    app.include_router(settings_router, prefix="/api")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, HTTPException, Query
    from pydantic import BaseModel
    _FASTAPI = True
except ImportError:
    _FASTAPI = False
    logger.warning("FastAPI not installed — settings routes unavailable")


if _FASTAPI:
    router = APIRouter(tags=["settings"])

    class SettingUpdate(BaseModel):
        value: Any

    # ── GET all settings ──────────────────────────────────────────────────────

    @router.get("/settings", response_model=list[dict])
    async def get_settings(category: Optional[str] = Query(None)):
        from core.config_registry import config
        return config.as_api_dict(category=category)

    # ── GET single setting ────────────────────────────────────────────────────

    @router.get("/settings/{key:path}")
    async def get_setting(key: str):
        from core.config_registry import config, get_entry, _REGISTRY_MAP
        if key not in _REGISTRY_MAP:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
        entries = config.as_api_dict()
        match = next((e for e in entries if e["key"] == key), None)
        if not match:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
        return match

    # ── PUT update setting ────────────────────────────────────────────────────

    @router.put("/settings/{key:path}")
    async def update_setting(key: str, body: SettingUpdate):
        from core.config_registry import config, _REGISTRY_MAP
        if key not in _REGISTRY_MAP:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

        try:
            config.set(key, body.value)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        entry = _REGISTRY_MAP[key]
        return {
            "key": key,
            "value": config.get(key),
            "restart_required": entry.restart_required,
            "message": "Setting updated. Restart required." if entry.restart_required else "Setting updated.",
        }

    # ── POST bulk update ──────────────────────────────────────────────────────

    @router.post("/settings/bulk")
    async def bulk_update_settings(updates: dict[str, Any]):
        from core.config_registry import config, _REGISTRY_MAP
        results = {}
        errors = {}
        restart_needed = False

        for key, value in updates.items():
            if key not in _REGISTRY_MAP:
                errors[key] = f"Unknown key: {key}"
                continue
            try:
                config.set(key, value)
                results[key] = config.get(key)
                if _REGISTRY_MAP[key].restart_required:
                    restart_needed = True
            except Exception as e:
                errors[key] = str(e)

        return {
            "updated": results,
            "errors": errors,
            "restart_required": restart_needed,
        }

    # ── POST reset all ────────────────────────────────────────────────────────

    @router.post("/settings/reset")
    async def reset_all_settings():
        from core.config_registry import config
        config.reset_all()
        return {"message": "All settings reset to defaults (env vars and yaml still apply)"}

    # ── POST reset single ─────────────────────────────────────────────────────

    @router.post("/settings/reset/{key:path}")
    async def reset_setting(key: str):
        from core.config_registry import config, _REGISTRY_MAP
        if key not in _REGISTRY_MAP:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
        config.reset(key)
        return {"key": key, "value": config.get(key), "message": "Reset to default"}

    # ── GET model list ────────────────────────────────────────────────────────

    @router.get("/models")
    async def list_models():
        from core.config_registry import config
        import httpx

        ollama_url = config.get("ollama.base_url")
        ollama_models = []
        error = None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{ollama_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                raw_models = data.get("models", [])
                ollama_models = [
                    {
                        "id": f"ollama/{m['name']}",
                        "name": m["name"],
                        "provider": "ollama",
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                    for m in raw_models
                ]
        except Exception as e:
            error = str(e)
            logger.warning(f"Could not fetch Ollama models: {e}")

        cloud_models = []
        if config.get("failover.openai_api_key"):
            cloud_models.extend([
                {"id": "openai/gpt-4o-mini", "name": "gpt-4o-mini", "provider": "openai"},
                {"id": "openai/gpt-4o",      "name": "gpt-4o",      "provider": "openai"},
            ])
        if config.get("failover.anthropic_api_key"):
            cloud_models.extend([
                {"id": "anthropic/claude-3-haiku-20240307",     "name": "claude-3-haiku",   "provider": "anthropic"},
                {"id": "anthropic/claude-3-5-sonnet-20241022",  "name": "claude-3-5-sonnet", "provider": "anthropic"},
            ])

        return {
            "ollama_url": ollama_url,
            "ollama_available": error is None,
            "ollama_error": error,
            "models": ollama_models + cloud_models,
            "total": len(ollama_models) + len(cloud_models),
        }

    # ── GET model groups ──────────────────────────────────────────────────────

    @router.get("/models/groups")
    async def get_model_groups():
        from core.config_registry import config

        groups = {
            "chat":         config.get("llm.chat_model"),
            "code":         config.get("llm.code_model"),
            "analysis":     config.get("llm.analysis_model"),
            "reasoning":    config.get("llm.reasoning_model"),
            "vision":       config.get("llm.vision_model"),
            "embedding":    config.get("llm.embedding_model"),
            "fallback":     config.get("llm.fallback_model"),
            "orchestrator": config.get("llm.orchestrator_model"),
        }
        reasoning_group = config.get("model_groups.reasoning_group")

        return {
            "groups": groups,
            "reasoning_engine_uses": reasoning_group,
            "effective_reasoning_model": groups.get(reasoning_group, groups["chat"]),
        }

    # ── GET categories ────────────────────────────────────────────────────────

    @router.get("/settings/meta/categories")
    async def get_categories():
        from core.config_registry import all_categories, entries_by_category
        return [
            {
                "id": cat,
                "label": cat.replace("_", " ").title(),
                "count": len(entries_by_category(cat)),
            }
            for cat in all_categories()
        ]

else:
    class router:
        pass
