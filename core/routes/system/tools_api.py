"""Headless tools API — list, describe and execute JARVIS native tools.

A *native* tool is an in-process capability (no subprocess, no network unless
the tool itself reaches out). The registry is the single source of truth for
the headless CLI/TUI: ``list_tools`` enumerates, ``get_tool_schema`` describes
and ``execute_tool`` runs one with a plain argument dict.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

NATIVE_TOOLS: dict[str, dict[str, Any]] = {}


# ── registry ─────────────────────────────────────────────────────────────
def register_native_tool(
    name: str,
    handler: Callable,
    description: str = "",
    args_schema: Optional[dict] = None,
    required: Optional[list] = None,
    replace: bool = False,
) -> None:
    """Register (or, with *replace*, overwrite) a native tool."""
    if name in NATIVE_TOOLS and not replace:
        raise ValueError(f"native tool already registered: {name}")
    NATIVE_TOOLS[name] = {
        "kind": "native",
        "description": description,
        "handler": handler,
        "args": dict(args_schema or {}),
        "required": list(required or []),
    }


def unregister_native_tool(name: str) -> bool:
    return NATIVE_TOOLS.pop(name, None) is not None


# ── built-in tools (lazy imports keep startup cheap + cycle-free) ────────
def _tool_list_models(**_kwargs: Any) -> dict:
    from jarvis_provider import list_models
    return list_models()


def _tool_get_model(role: str = "chat", **_kwargs: Any) -> dict:
    from jarvis_provider import get_model
    return {"role": role, "model": get_model(role)}


def _tool_collect_metrics(**_kwargs: Any) -> dict:
    from core.observability.metrics import collect_metrics
    return collect_metrics()


def _tool_resource_snapshot(**_kwargs: Any) -> dict:
    from monitors.resource import resource_monitor
    return resource_monitor.snapshot().to_dict()


def _tool_system_stats(**_kwargs: Any) -> dict:
    from core.workspace.process_monitor import ProcessMonitor
    return ProcessMonitor().get_system_stats()


def _tool_list_providers(**_kwargs: Any) -> dict:
    from core.providers.store import list_known_providers
    return {"providers": list_known_providers()}


def _register_builtins() -> None:
    register_native_tool(
        "list_models", _tool_list_models,
        description="Show the model configured for each LLM role.",
        args_schema={},
    )
    register_native_tool(
        "get_model", _tool_get_model,
        description="Return the model id configured for a role.",
        args_schema={"role": {"type": "string", "default": "chat"}},
    )
    register_native_tool(
        "collect_metrics", _tool_collect_metrics,
        description="Snapshot process metrics.",
        args_schema={},
    )
    register_native_tool(
        "resource_snapshot", _tool_resource_snapshot,
        description="Snapshot CPU/RAM/disk/GPU resource usage.",
        args_schema={},
    )
    register_native_tool(
        "system_stats", _tool_system_stats,
        description="Read-only system statistics (CPU, RAM).",
        args_schema={},
    )
    register_native_tool(
        "list_providers", _tool_list_providers,
        description="List the providers JARVIS knows how to install.",
        args_schema={},
    )


_register_builtins()


# ── request/response models ──────────────────────────────────────────────
class ToolExecuteRequest(BaseModel):
    """Payload for executing one native tool."""

    tool: str
    args: dict = Field(default_factory=dict)


class ToolExecuteResponse(BaseModel):
    """Result of a native tool execution."""

    success: bool
    tool: str
    result: Any = None
    error: str = ""


# ── API ──────────────────────────────────────────────────────────────────
async def list_tools() -> dict:
    """Enumerate the registered native tools."""
    tools = [{"name": name, "kind": spec["kind"]}
             for name, spec in sorted(NATIVE_TOOLS.items())]
    return {"count": len(tools), "tools": tools}


async def get_tool_schema(tool: str) -> dict:
    """Describe one native tool, including its argument schema."""
    spec = NATIVE_TOOLS.get(tool)
    if spec is None:
        return {"name": tool, "kind": "unknown", "input": {}, "found": False}
    return {
        "name": tool,
        "kind": spec["kind"],
        "description": spec["description"],
        "input": {
            "type": "object",
            "args": dict(spec.get("args") or {}),
            "required": list(spec.get("required") or []),
        },
        "found": True,
    }


async def execute_tool(tool: str, args: Optional[dict] = None) -> dict:
    """Execute a native tool by name; never raises."""
    spec = NATIVE_TOOLS.get(tool)
    if spec is None:
        return {"success": False, "tool": tool, "result": None,
                "error": f"unknown tool: {tool}"}
    try:
        outcome = spec["handler"](**dict(args or {}))
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return {"success": True, "tool": tool, "result": outcome, "error": ""}
    except Exception as exc:  # noqa: BLE001 — tool errors are data
        logger.debug("[tools_api] %s failed: %s", tool, exc)
        return {"success": False, "tool": tool, "result": None, "error": str(exc)}


async def execute_request(request: ToolExecuteRequest) -> dict:
    """Route handler form of ``execute_tool``."""
    return await execute_tool(request.tool, request.args)


def register_routes(app: Any) -> None:
    """Attach the headless tools endpoints to a FastAPI-style app."""
    try:
        app.add_api_route("/api/system/tools", list_tools, methods=["GET"])
        app.add_api_route("/api/system/tools/{tool}", get_tool_schema,
                          methods=["GET"])
        app.add_api_route("/api/system/tools/execute", execute_request,
                          methods=["POST"])
    except Exception:  # noqa: BLE001 — registration is optional
        pass


__all__ = [
    "NATIVE_TOOLS",
    "register_native_tool",
    "unregister_native_tool",
    "ToolExecuteRequest",
    "ToolExecuteResponse",
    "list_tools",
    "get_tool_schema",
    "execute_tool",
    "execute_request",
    "register_routes",
]
