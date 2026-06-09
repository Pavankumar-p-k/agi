# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Callable, Iterable, List, Optional

from .base_tool import ToolDefinition, ToolResult


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

    def as_dicts(self) -> list[dict]:
        """Machine-readable catalog for API consumption."""
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

    def catalog(self) -> str:
        """Human-readable string for LLM system prompt. Description IS routing."""
        if not self._definitions:
            return "AVAILABLE TOOLS: (none)"
        lines = ["AVAILABLE TOOLS:"]
        for t in self._definitions.values():
            lines.append(f"\n- {t.name}: {t.description}")
            lines.append(f"  params: {json.dumps(t.input_schema)}")
            if t.examples:
                ex = t.examples[0]
                inp = json.dumps(ex.get("input", {}))
                out = str(ex.get("output", ""))[:80]
                lines.append(f"  example: input={inp} -> output={out}")
        lines.append(
            '\nTo call a tool output exactly: {"tool": "name", "params": {...}}'
        )
        return "\n".join(lines)

    def get_handler_dict(self, names: list[str] | None = None) -> dict[str, Callable]:
        tools = self.list()
        if names is not None:
            tools = [t for t in tools if t.name in names]
        return {
            t.name: t.handler
            for t in tools
            if t.handler is not None
        }

    async def execute(self, name: str, params: dict) -> ToolResult:
        tool = self._definitions.get(name)
        if not tool:
            return ToolResult(
                error=f"Unknown tool: '{name}'. Available: {list(self._definitions.keys())}",
                retryable=False,
            )
        if not tool.handler:
            return ToolResult(error=f"Tool '{name}' has no handler", retryable=False)
        try:
            result = await tool.handler(**params) if hasattr(tool.handler, '__await__') else tool.handler(**params)
            return ToolResult(output=str(result))
        except TypeError as e:
            return ToolResult(
                error=f"Wrong params for '{name}': {e}. Schema: {json.dumps(tool.input_schema)}",
                retryable=True,
            )
        except Exception as e:
            return ToolResult(error=f"'{name}' failed: {str(e)}", retryable=True)

    def __len__(self) -> int:
        return len(self._definitions)


def new_registry() -> ToolRegistry:
    return ToolRegistry()


_default_tool_registry = new_registry()


def get_tool(name: str) -> ToolDefinition:
    return _default_tool_registry.get(name)
