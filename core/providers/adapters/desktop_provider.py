"""DesktopProvider — exposes the desktop controller as a normal provider.

Gate 10: the desktop is just another capability provider. Safety and
replay live behind the controller; the provider maps task dicts to
controller primitives and reports honest results.
"""
from __future__ import annotations

import asyncio
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

# Action name -> (capability permission id, action type).
_ACTIONS = {
    "mouse_move": "desktop.mouse.move",
    "mouse_click": "desktop.mouse.click",
    "keyboard_type": "desktop.keyboard.type",
    "screen_capture": "desktop.screen.capture",
    "window_focus": "desktop.window.focus",
}


class DesktopProvider(ExecutionProvider):
    """Drives core.desktop through the standard provider contract."""

    provider_id = "desktop"
    name = "Desktop Controller"
    version = "1.0.0"
    priority = 60

    def __init__(self) -> None:
        from core.desktop.controller import DesktopController
        from core.desktop.replay import ReplayGraph
        from core.desktop.safety import SafetyManager
        # Own instances: the provider must not consume the module-level
        # singletons' safety state (tests reset those independently).
        self.controller = DesktopController(
            safety=SafetyManager(), replay=ReplayGraph())

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["desktop"],
            version=self.version,
            features=["mouse", "keyboard", "screen", "windows"],
            languages=[],
            modalities=["desktop"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.HEALTHY,
                              detail="desktop controller ready")

    async def execute(self, task: dict, context: Any = None) -> ExecutionResult:
        task = dict(task or {})
        action = str(task.get("action", "")).strip()
        if not action or action not in _ACTIONS:
            return ExecutionResult(
                success=False,
                error=f"Unknown desktop action: {action!r}",
                provider_id=self.provider_id,
            )

        try:
            result = await self._dispatch(action, task)
        except Exception as exc:  # noqa: BLE001 — backend errors surface honestly
            return ExecutionResult(success=False, error=str(exc),
                                   provider_id=self.provider_id)
        return result

    async def _dispatch(self, action: str, task: dict) -> ExecutionResult:
        from core.desktop.safety import DesktopActionType

        if action == "mouse_move":
            r = self.controller.move_mouse(int(task.get("x", 0)),
                                           int(task.get("y", 0)))
        elif action == "mouse_click":
            r = self.controller.click(int(task.get("x", 0)),
                                      int(task.get("y", 0)))
        elif action == "keyboard_type":
            r = self.controller.type_text(str(task.get("text", "")))
        elif action == "screen_capture":
            r = await self._capture()
        else:  # window_focus
            r = self.controller.focus_window(str(task.get("window_title", "")))
        return ExecutionResult(
            success=r.success,
            output=str(getattr(r, "output", "") or ""),
            error=str(getattr(r, "reason", "") or getattr(r, "error", "") or ""),
            provider_id=self.provider_id,
            metadata={"replay": self.controller.replay.to_dict()[-5:]},
        )

    async def _capture(self):
        from core.desktop.controller import ActionResult
        try:
            capture = self.controller.capture_screen()
        except Exception as exc:  # noqa: BLE001
            return ActionResult(success=False, action="screen_capture",
                                error=str(exc))
        return capture


desktop_provider = DesktopProvider()


__all__ = ["DesktopProvider", "desktop_provider"]
