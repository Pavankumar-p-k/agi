"""Incremental bridge from legacy desktop handlers to the canonical registry."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tools.base_tool import ToolDefinition
from tools.registry import ToolRegistry


def register_desktop_tools(
    registry: ToolRegistry,
    tools: Mapping[str, Callable[..., Any]],
    *,
    descriptions: Mapping[str, str] | None = None,
    owner_module: str = "Desktop AI",
) -> ToolRegistry:
    """Register existing desktop handlers without changing their call shape.

    The legacy agent can continue invoking its mapping directly while new
    callers use the shared registry. This keeps migration additive and avoids
    duplicating handler implementations.
    """
    descriptions = descriptions or {}
    for name, handler in tools.items():
        registry.register(
            ToolDefinition(
                name=name,
                description=descriptions.get(name, f"Desktop capability: {name}"),
                category="desktop",
                handler=handler,
                metadata={"owner_module": owner_module, "source": "legacy_desktop_tools"},
            ),
            owner_module=owner_module,
        )
    return registry
