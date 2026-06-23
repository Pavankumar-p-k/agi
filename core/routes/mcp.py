"""core/routes/mcp.py — MCP Tools REST API."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

if _FASTAPI:
    router = APIRouter(tags=["mcp"])

    @router.get("/mcp/tools")
    async def list_mcp_tools():
        try:
            from mcp.server import mcp_server
            defs = mcp_server.get_tool_definitions() if hasattr(mcp_server, "get_tool_definitions") else []
            tools = []
            for d in defs:
                tools.append({
                    "id": d.get("name", ""),
                    "name": d.get("name", ""),
                    "description": d.get("description", ""),
                    "input_schema": d.get("inputSchema", {}),
                })
            return {"tools": tools, "total": len(tools)}
        except Exception as e:
            logger.warning("[MCP] list_mcp_tools failed: %s", e)
            return {"tools": [], "total": 0, "error": str(e)}

else:
    class router:
        pass
