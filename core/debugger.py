"""Server-side debug API for runtime introspection."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jarvis.debugger")


def runtime_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}

    # Active sessions
    try:
        from core.session import list_sessions
        sessions = list_sessions()
        snapshot["sessions"] = [
            {"session_id": s.get("session_id", ""), "message_count": s.get("message_count", 0)}
            for s in (sessions or [])
        ]
    except Exception as e:
        snapshot["sessions"] = f"unavailable: {e}"

    # Tool registry
    try:
        from core.tools.execution import get_registered_tools
        tools = get_registered_tools()
        snapshot["tools"] = list(tools.keys()) if tools else []
    except Exception as _e:
        logger.debug("debugger snapshot tools failed: %s", _e)
        snapshot["tools"] = "unavailable"

    # Plugins
    try:
        from core.plugins.loader import plugin_registry
        snapshot["plugins"] = [
            {"name": p.manifest.name, "version": p.manifest.version, "enabled": p.enabled}
            for p in plugin_registry.values()
        ]
    except Exception as _e:
        logger.debug("debugger snapshot plugins failed: %s", _e)
        snapshot["plugins"] = "unavailable"

    # Config summary
    try:
        from core.config import jarvis_config
        db = jarvis_config.db
        snapshot["config"] = {
            "db_url": db.url if db else "N/A",
            "debug": jarvis_config.debug if hasattr(jarvis_config, "debug") else False,
        }
    except Exception as _e:
        logger.debug("debugger snapshot config failed: %s", _e)
        snapshot["config"] = "unavailable"

    return snapshot
