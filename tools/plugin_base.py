from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .base_tool import ToolDefinition, ToolResult
from .registry import ToolRegistry, new_registry


@dataclass
class ToolAvailability:
    """Availability expression for a tool. Inspired by OpenClaw's ToolAvailabilityExpression."""
    always: bool = False
    requires_auth: bool = False
    requires_config: Optional[str] = None
    requires_env: Optional[str] = None

    def is_available(self, context: dict[str, Any] | None = None) -> bool:
        if self.always:
            return True
        ctx = context or {}
        if self.requires_auth and not ctx.get("authenticated"):
            return False
        if self.requires_config and self.requires_config not in ctx.get("config", {}):
            return False
        if self.requires_env:
            import os
            if not os.getenv(self.requires_env):
                return False
        return True


class ToolPlugin:
    """Plugin-like tool registration with availability and lifecycle.

    Patterns borrowed from OpenClaw's defineToolPlugin + tool() factory.
    """

    def __init__(self, name: str, description: str, registry: ToolRegistry | None = None):
        self.name = name
        self.description = description
        self.registry = registry or new_registry()
        self._tools: list[ToolDefinition] = []

    def tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        category: str = "general",
        input_schema: dict[str, Any] | None = None,
        availability: ToolAvailability | None = None,
        read_only: bool = False,
        risk_tags: list[str] | None = None,
    ) -> ToolDefinition:
        definition = ToolDefinition(
            name=name,
            description=description,
            category=category,
            input_schema=input_schema or {},
            handler=handler,
            read_only=read_only,
            risk_tags=risk_tags or [],
            metadata={
                "plugin": self.name,
                "availability": availability.__dict__ if availability else {"always": True},
            },
        )
        self._tools.append(definition)
        self.registry.register(definition)
        return definition

    def register_all(self) -> list[ToolDefinition]:
        return list(self._tools)


def define_tool_plugin(
    name: str,
    description: str,
    registry: ToolRegistry | None = None,
) -> ToolPlugin:
    """Factory for creating a ToolPlugin. Mirrors OpenClaw's defineToolPlugin."""
    return ToolPlugin(name=name, description=description, registry=registry)
