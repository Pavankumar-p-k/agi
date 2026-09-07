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
import threading
from collections import OrderedDict
from typing import Any, Callable, Iterable, List, Optional

from .base_tool import ToolDefinition, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: OrderedDict[str, ToolDefinition] = OrderedDict()
        self._lock = threading.Lock()

    def register(self, definition: ToolDefinition) -> ToolDefinition:
        with self._lock:
            self._definitions[definition.name] = definition
        return definition

    def extend(self, definitions: Iterable[ToolDefinition]) -> None:
        with self._lock:
            for definition in definitions:
                self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        with self._lock:
            return self._definitions[name]

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._definitions

    def list(self, *, category: Optional[str] = None) -> List[ToolDefinition]:
        with self._lock:
            items = list(self._definitions.values())
        if category:
            items = [item for item in items if item.category == category]
        return items

    def as_dicts(self) -> list[dict]:
        with self._lock:
            definitions = list(self._definitions.values())
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
            for definition in definitions
        ]

    def catalog(self) -> str:
        with self._lock:
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
        with self._lock:
            tools = list(self._definitions.values())
        if names is not None:
            tools = [t for t in tools if t.name in names]
        return {
            t.name: t.handler
            for t in tools
            if t.handler is not None
        }

    async def execute(self, name: str, params: dict) -> ToolResult:
        with self._lock:
            tool = self._definitions.get(name)
        if not tool:
            with self._lock:
                available = list(self._definitions.keys())
            return ToolResult(
                error=f"Unknown tool: '{name}'. Available: {available}",
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
        with self._lock:
            return len(self._definitions)


def new_registry() -> ToolRegistry:
    return ToolRegistry()


_default_tool_registry_lock = threading.Lock()
_default_tool_registry: ToolRegistry | None = None


def _ensure_registry() -> ToolRegistry:
    global _default_tool_registry
    if _default_tool_registry is not None:
        return _default_tool_registry
    with _default_tool_registry_lock:
        if _default_tool_registry is None:
            _default_tool_registry = new_registry()
    return _default_tool_registry


def get_tool(name: str) -> ToolDefinition:
    return _ensure_registry().get(name)
