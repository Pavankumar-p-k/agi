"""core/routes/integrations.py — Integration Management REST API."""
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

if _FASTAPI:
    router = APIRouter(tags=["integrations"])

    class IntegrationConnectRequest(BaseModel):
        credentials: dict[str, Any] = {}

    @router.get("/api/integrations")
    async def list_integrations():
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        return {"integrations": mgr.list_integrations()}

    @router.get("/api/integrations/{name}")
    async def get_integration(name: str):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        integ = mgr.get(name)
        if not integ:
            raise HTTPException(status_code=404, detail=f"Integration '{name}' not found")
        status = await mgr.health_check(name)
        return {
            "name": integ.name,
            "connected": integ._connected,
            "status": status.to_dict(),
        }

    @router.get("/api/integrations/{name}/status")
    async def get_integration_status(name: str):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        status = await mgr.health_check(name)
        return status.to_dict()

    @router.post("/api/integrations/{name}/connect")
    async def connect_integration(name: str, body: IntegrationConnectRequest = IntegrationConnectRequest()):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        ok = await mgr.connect(name, **body.credentials)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Failed to connect '{name}'")
        return {"name": name, "connected": True}

    @router.post("/api/integrations/{name}/disconnect")
    async def disconnect_integration(name: str):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        ok = await mgr.disconnect(name)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Failed to disconnect '{name}'")
        return {"name": name, "connected": False}

    @router.get("/api/integrations/{name}/config")
    async def get_integration_config(name: str):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        integ = mgr.get(name)
        if not integ:
            raise HTTPException(status_code=404, detail=f"Integration '{name}' not found")
        return {"name": name, "config": integ._config}

    @router.post("/api/integrations/{name}/config")
    async def set_integration_config(name: str, body: dict[str, Any]):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        integ = mgr.get(name)
        if not integ:
            raise HTTPException(status_code=404, detail=f"Integration '{name}' not found")
        integ._config.update(body)
        integ._save_config()
        return {"name": name, "config": integ._config}

    @router.post("/api/integrations/{name}/send")
    async def send_via_integration(name: str, body: dict):
        target = body.get("target", "")
        message = body.get("message", "")
        if not target or not message:
            raise HTTPException(status_code=400, detail="target and message are required")
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        ok = await mgr.send(name, target, message, **body.get("kwargs", {}))
        return {"sent": ok}

    @router.post("/api/integrations/health")
    async def all_integrations_health():
        from core.integration_manager import health_check_all
        results = await health_check_all()
        return {"integrations": results}

    @router.post("/api/integrations/{name}/test")
    async def test_integration(name: str):
        from core.integration_manager import get_integration_manager
        mgr = get_integration_manager()
        status = await mgr.health_check(name)
        return status.to_dict()
else:
    class router:
        pass
