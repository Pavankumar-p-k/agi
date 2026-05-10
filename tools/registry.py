from __future__ import annotations

from collections import OrderedDict
from typing import Iterable, List, Optional

from .base_tool import ToolDefinition


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: OrderedDict[str, ToolDefinition] = OrderedDict()

    def register(self, definition: ToolDefinition) -> ToolDefinition:
        self._definitions[definition.name] = definition
        return definition

    def extend(self, definitions: Iterable[ToolDefinition]) -> None:
        for definition in definitions:
            self.register(definition)

    def get(self, name: str) -> ToolDefinition:
        return self._definitions[name]

    def has(self, name: str) -> bool:
        return name in self._definitions

    def list(self, *, category: Optional[str] = None) -> List[ToolDefinition]:
        items = list(self._definitions.values())
        if category:
            items = [item for item in items if item.category == category]
        return items

    def catalog(self) -> list[dict]:
        return [
            {
                "name": definition.name,
                "description": definition.description,
                "category": definition.category,
                "permission": definition.permission,
                "input_schema": dict(definition.input_schema),
                "capabilities": list(definition.capabilities),
                "risk_tags": list(definition.risk_tags),
                "read_only": definition.read_only,
                "metadata": dict(definition.metadata),
            }
            for definition in self._definitions.values()
        ]

    def __len__(self) -> int:
        return len(self._definitions)


def new_registry() -> ToolRegistry:
    return ToolRegistry()

_default_tool_registry = new_registry()


def get_tool(name: str) -> ToolDefinition:
    return _default_tool_registry.get(name)
