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

from .base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    ReliabilityMetrics,
    RiskTier,
    ToolDefinition,
    ToolResult,
    VerificationSpec,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: OrderedDict[str, ToolDefinition] = OrderedDict()
        self._capabilities: OrderedDict[str, CapabilityDefinition] = OrderedDict()
        self._lock = threading.Lock()

    def register(self, definition: ToolDefinition | CapabilityDefinition, owner_module: str = "Core") -> ToolDefinition:
        with self._lock:
            if isinstance(definition, CapabilityDefinition):
                self._capabilities[definition.name] = definition
                tool_def = definition.to_tool_definition()
                self._definitions[definition.name] = tool_def
                return tool_def
            else:
                self._definitions[definition.name] = definition
                if definition.name not in self._capabilities:
                    self._capabilities[definition.name] = definition.to_capability_definition(owner_module=owner_module)
                return definition

    def register_capability(self, capability: CapabilityDefinition) -> CapabilityDefinition:
        with self._lock:
            self._capabilities[capability.name] = capability
            self._definitions[capability.name] = capability.to_tool_definition()
        return capability

    def extend(self, definitions: Iterable[ToolDefinition | CapabilityDefinition]) -> None:
        with self._lock:
            for definition in definitions:
                if isinstance(definition, CapabilityDefinition):
                    self._capabilities[definition.name] = definition
                    self._definitions[definition.name] = definition.to_tool_definition()
                else:
                    self._definitions[definition.name] = definition
                    if definition.name not in self._capabilities:
                        self._capabilities[definition.name] = definition.to_capability_definition()

    def get(self, name: str) -> ToolDefinition:
        with self._lock:
            return self._definitions[name]

    def get_capability(self, name: str) -> CapabilityDefinition | None:
        with self._lock:
            return self._capabilities.get(name)

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._definitions or name in self._capabilities

    def has_capability(self, name: str) -> bool:
        with self._lock:
            return name in self._capabilities

    def list(self, *, category: Optional[str] = None) -> List[ToolDefinition]:
        with self._lock:
            items = list(self._definitions.values())
        if category:
            items = [item for item in items if item.category == category]
        return items

    def list_capabilities(
        self,
        *,
        owner_module: Optional[str] = None,
        cap_type: Optional[CapabilityType | str] = None,
        health: Optional[CapabilityHealth | str] = None,
        risk: Optional[RiskTier | str] = None,
        status: Optional[CapabilityStatus | str] = None,
    ) -> List[CapabilityDefinition]:
        with self._lock:
            items = list(self._capabilities.values())
        if owner_module:
            owner_module_lower = owner_module.lower()
            items = [c for c in items if c.owner_module.lower() == owner_module_lower]
        if cap_type:
            type_val = cap_type.value if isinstance(cap_type, CapabilityType) else cap_type
            items = [c for c in items if c.type.value == type_val]
        if health:
            health_val = health.value if isinstance(health, CapabilityHealth) else health
            items = [c for c in items if c.health.value == health_val]
        if risk:
            risk_val = risk.value if isinstance(risk, RiskTier) else risk
            items = [c for c in items if c.risk.value == risk_val]
        if status:
            status_val = status.value if isinstance(status, CapabilityStatus) else status
            items = [c for c in items if c.status.value == status_val]
        return items

    def record_execution(self, name: str, success: bool, failure_reason: str | None = None) -> ReliabilityMetrics | None:
        with self._lock:
            cap = self._capabilities.get(name)
            if not cap:
                return None
            if success:
                cap.reliability.record_success()
                if cap.health in (CapabilityHealth.DEGRADED, CapabilityHealth.UNHEALTHY) and cap.reliability.consecutive_failures == 0:
                    cap.health = CapabilityHealth.HEALTHY
            else:
                cap.reliability.record_failure(failure_reason)
                if cap.reliability.consecutive_failures >= 3:
                    cap.health = CapabilityHealth.DEGRADED
                if cap.reliability.consecutive_failures >= 5:
                    cap.health = CapabilityHealth.UNHEALTHY
            if name in self._definitions:
                self._definitions[name].metadata["reliability_score"] = cap.reliability.score
                self._definitions[name].metadata["health"] = cap.health.value
            return cap.reliability

    def set_capability_health(self, name: str, health: CapabilityHealth, reason: str | None = None) -> bool:
        with self._lock:
            cap = self._capabilities.get(name)
            if not cap:
                return False
            cap.health = health
            if reason:
                cap.metadata["last_health_reason"] = reason
            if name in self._definitions:
                self._definitions[name].metadata["health"] = health.value
            return True

    def run_health_checks(self) -> dict[str, CapabilityHealth]:
        results: dict[str, CapabilityHealth] = {}
        with self._lock:
            caps = list(self._capabilities.values())
        for cap in caps:
            if cap.health_check:
                try:
                    ok = cap.health_check()
                    health = CapabilityHealth.HEALTHY if ok else CapabilityHealth.UNHEALTHY
                    self.set_capability_health(cap.name, health)
                    results[cap.name] = health
                except Exception as ex:
                    self.set_capability_health(cap.name, CapabilityHealth.UNHEALTHY, reason=str(ex))
                    results[cap.name] = CapabilityHealth.UNHEALTHY
            else:
                results[cap.name] = cap.health
        return results

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

    def capabilities_as_dicts(self) -> list[dict]:
        with self._lock:
            caps = list(self._capabilities.values())
        return [cap.to_dict() for cap in caps]

    def catalog(self) -> str:
        with self._lock:
            if not self._definitions and not self._capabilities:
                return "AVAILABLE TOOLS & CAPABILITIES: (none)"
            lines = ["AVAILABLE CAPABILITIES:"]
            for cap in self._capabilities.values():
                status_icon = "✓" if cap.health == CapabilityHealth.HEALTHY else ("!" if cap.health == CapabilityHealth.DEGRADED else "✗")
                lines.append(f"\n- [{status_icon}] {cap.name} ({cap.owner_module}) [{cap.type.value}] - Reliability: {int(cap.reliability.score*100)}%")
                lines.append(f"  {cap.description}")
                lines.append(f"  params: {json.dumps(cap.inputs)}")
                if cap.requirements:
                    lines.append(f"  requires: {', '.join(cap.requirements)}")
            lines.append(
                '\nTo call a tool output exactly: {\"tool\": \"name\", \"params\": {...}}'
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
            cap = self._capabilities.get(name)
        if not tool:
            with self._lock:
                available = list(self._definitions.keys())
            self.record_execution(name, success=False, failure_reason="Unknown tool")
            return ToolResult(
                error=f"Unknown tool: '{name}'. Available: {available}",
                retryable=False,
            )
        handler = tool.handler or (cap.handler if cap else None)
        if not handler:
            self.record_execution(name, success=False, failure_reason="No handler")
            return ToolResult(error=f"Tool '{name}' has no handler", retryable=False)
        try:
            result = await handler(**params) if hasattr(handler, '__await__') else handler(**params)
            res = ToolResult(output=str(result))
            self.record_execution(name, success=True)
            return res
        except TypeError as e:
            err = f"Wrong params for '{name}': {e}. Schema: {json.dumps(tool.input_schema)}"
            self.record_execution(name, success=False, failure_reason=err)
            return ToolResult(
                error=err,
                retryable=True,
            )
        except Exception as e:
            err = f"'{name}' failed: {str(e)}"
            self.record_execution(name, success=False, failure_reason=err)
            return ToolResult(error=err, retryable=True)

    def __len__(self) -> int:
        with self._lock:
            return max(len(self._definitions), len(self._capabilities))


# Single Authoritative Registry alias
CapabilityRegistry = ToolRegistry


def new_registry() -> ToolRegistry:
    return ToolRegistry()


def new_capability_registry() -> ToolRegistry:
    return new_registry()


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


def get_capability(name: str) -> CapabilityDefinition | None:
    return _ensure_registry().get_capability(name)
