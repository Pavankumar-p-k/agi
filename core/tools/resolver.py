"""ToolResolver — separates tool name → handler mapping from execution.

Engines call ``resolve()`` to find a handler for a tool name instead of
importing handler internals directly.  No engine should know tool
implementation details.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from core.tools._constants import TOOL_TAGS
from core.tools.execution.mcp import _MCP_TOOL_MAP
from core.tools.execution.plugins import _PLUGIN_TOOL_HANDLERS

logger = logging.getLogger(__name__)


class ResolutionResult:
    """Result of a tool resolution."""
    def __init__(self, handler: Callable | None = None,
                 source: str = "", tool_name: str = "") -> None:
        self.handler = handler
        self.source = source
        self.tool_name = tool_name

    @property
    def found(self) -> bool:
        return self.handler is not None


_NATIVE_TOOL_HANDLERS: dict[str, str] = {}


def _get_native_handler_map() -> dict[str, str]:
    if not _NATIVE_TOOL_HANDLERS:
        from core.tools.execution.handlers import get_registered_tools
        _NATIVE_TOOL_HANDLERS.update(get_registered_tools())
    return _NATIVE_TOOL_HANDLERS


class ToolResolver:
    """Resolves a tool name to its handler.

    Resolution order:
      1. Native tool handlers (from ``_TOOL_HANDLERS`` dispatch table)
      2. MCP tool map
      3. Plugin tool handlers
      4. Registered tool tags
    """

    def resolve(self, tool_name: str) -> ResolutionResult:
        native = _get_native_handler_map()
        source = native.get(tool_name, "")

        if source == "native":
            return ResolutionResult(source="native", tool_name=tool_name)

        if tool_name in _MCP_TOOL_MAP:
            return ResolutionResult(
                handler=_MCP_TOOL_MAP.get(tool_name),
                source="mcp", tool_name=tool_name,
            )

        if tool_name in _PLUGIN_TOOL_HANDLERS:
            return ResolutionResult(
                handler=_PLUGIN_TOOL_HANDLERS.get(tool_name),
                source="plugin", tool_name=tool_name,
            )

        if tool_name in TOOL_TAGS:
            return ResolutionResult(source="tag", tool_name=tool_name)

        return ResolutionResult(tool_name=tool_name)

    def list_all(self) -> list[str]:
        native = _get_native_handler_map()
        names = set(native.keys())
        names.update(_MCP_TOOL_MAP.keys())
        names.update(_PLUGIN_TOOL_HANDLERS.keys())
        names.update(TOOL_TAGS)
        return sorted(names)

    def list_by_source(self, source: str) -> list[str]:
        if source == "native":
            return sorted(_get_native_handler_map().keys())
        if source == "mcp":
            return sorted(_MCP_TOOL_MAP.keys())
        if source == "plugin":
            return sorted(_PLUGIN_TOOL_HANDLERS.keys())
        return []


tool_resolver = ToolResolver()
