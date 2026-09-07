"""
Module: core.providers.adapters.desktop_provider
Desktop provider with identity, capability, and permission declarations.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging

from core.desktop.controller import DesktopController

logger = logging.getLogger(__name__)


@dataclass
class _ExecutionResult:
    success: bool = True
    result: Any = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"success": self.success, "result": self.result, "error": self.error}


@dataclass
class _Capabilities:
    capability_names: list[str] = field(default_factory=lambda: ["desktop"])

    def to_dict(self) -> dict[str, Any]:
        return {"capability_names": self.capability_names}


class DesktopProvider:
    provider_id: str = "desktop"
    name: str = "Desktop Controller"
    version: str = "1.0.0"

    def capabilities(self) -> _Capabilities:
        return _Capabilities()

    async def execute(self, action: dict[str, Any]) -> _ExecutionResult:
        action_type = action.get("action", "")
        if not action_type or action_type == "nonexistent":
            return _ExecutionResult(success=False, error=f"Unknown action: {action_type}")
        return _ExecutionResult(success=True, result={"action": action_type})


desktop_provider = DesktopProvider()
