from __future__ import annotations
import os
import logging
from fastapi import WebSocket, status

logger = logging.getLogger("jarvis.gateway.auth")

class BridgeAuth:
    """
    Simple token-based authentication for the MCP Bridge.
    Uses MCP_BRIDGE_TOKEN environment variable.
    """
    def __init__(self):
        self._token = os.getenv("MCP_BRIDGE_TOKEN", "")

    async def authenticate(self, websocket: WebSocket) -> bool:
        # 1. If no token configured, allow in dev mode
        if not self._token:
            logger.info("MCP Bridge: No token configured, allowing connection.")
            return True

        # 2. Check token in query parameters
        token = websocket.query_params.get("token")
        
        # 3. Check token in headers (Sec-WebSocket-Protocol or custom)
        if not token:
            auth_header = websocket.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ")
        
        if token == self._token:
            return True
            
        logger.warning(f"MCP Bridge: Unauthorized connection attempt from {websocket.client}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return False
