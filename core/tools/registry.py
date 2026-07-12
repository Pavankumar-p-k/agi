"""Canonical ToolRegistry — single authority for all tool definitions.

Replaces:
  - brain/tools/tool_registry.py (deprecated)
  - tools/registry.py (generic registry, kept for backwards compat)

Usage:
    from core.tools.registry import tool_registry
    tool_registry.register("my_tool", handler_fn, category="custom")
    tools = tool_registry.list_tools()
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from core.tools.execution.handlers import get_registered_tools as _get_native_tools

logger = logging.getLogger(__name__)


class ToolRecord:
    """Descriptor for a registered tool."""
    def __init__(self, name: str, handler: Callable | None = None,
                 category: str = "native", description: str = "") -> None:
        self.name = name
        self.handler = handler
        self.category = category
        self.description = description


class ToolRegistry:
    """Canonical tool registry — single authority for tool definitions.

    All execution paths query this registry to discover available tools.
    No engine should know tool implementation details.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolRecord] = {}

    def register(self, name: str, handler: Callable | None = None,
                 category: str = "native", description: str = "") -> None:
        self._tools[name] = ToolRecord(
            name=name, handler=handler,
            category=category, description=description,
        )

    def get(self, name: str) -> ToolRecord | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self, category: str | None = None) -> list[ToolRecord]:
        if category:
            return [t for t in self._tools.values() if t.category == category]
        return list(self._tools.values())

    def list_names(self, category: str | None = None) -> list[str]:
        return [t.name for t in self.list_tools(category)]

    def count(self) -> int:
        return len(self._tools)

    def discover_native(self) -> None:
        """Auto-discover all native tools from the execution handlers."""
        for name in _get_native_tools():
            if name not in self._tools:
                self.register(name, category="native")

    def discover_plugin(self, plugin_tools: dict[str, Callable]) -> None:
        """Register plugin-provided tools."""
        for name, handler in plugin_tools.items():
            self.register(name, handler, category="plugin")


tool_registry = ToolRegistry()
