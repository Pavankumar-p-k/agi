from __future__ import annotations

import logging
import time
from typing import Any

from core.desktop.controller import DesktopController, desktop_controller
from core.desktop.screen import ScreenCapture, screen_capture
from core.desktop.window import WindowController, window_controller
from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class DesktopProvider(ExecutionProvider):
    provider_id = "desktop"
    name = "Desktop Controller"
    version = "1.0.0"
    priority = 10
    installed = True
    _enabled = True

    def __init__(self) -> None:
        super().__init__()
        self._controller: DesktopController | None = None
        self._screen: ScreenCapture | None = None
        self._window: WindowController | None = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["desktop"],
            features=[
                "mouse_move", "mouse_click", "mouse_double_click",
                "mouse_scroll", "mouse_drag",
                "keyboard_type", "keyboard_press", "keyboard_hotkey",
                "screen_capture", "window_capture", "region_capture",
                "window_focus", "window_minimize", "window_maximize",
                "window_restore", "window_close",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            import pyautogui
            pyautogui.size()
            return ProviderHealth(
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_checked=time.time(),
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                error=f"Desktop unavailable: {e}",
                last_checked=time.time(),
            )

    async def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> ExecutionResult:
        start = time.monotonic()
        action = task.get("action", "")
        ctrl = desktop_controller
        screen = screen_capture
        win = window_controller

        try:
            result = self._dispatch(action, ctrl, screen, win, task)
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=result.get("success", False),
                output=result.get("output", ""),
                error=result.get("error", ""),
                exit_code=0 if result.get("success") else 1,
                duration_ms=elapsed,
                metadata={
                    "provider": "desktop",
                    "action": action,
                    "replay_node_id": result.get("replay_node_id", ""),
                },
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[DesktopProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False, output="", error=str(e),
                exit_code=1, duration_ms=elapsed,
                metadata={"provider": "desktop", "action": action},
            )

    def _dispatch(self, action: str, ctrl: DesktopController,
                  screen: ScreenCapture, win: WindowController,
                  task: dict[str, Any]) -> dict:
        # Mouse actions
        if action == "move_mouse":
            da = ctrl.move_mouse(task.get("x", 0), task.get("y", 0), task.get("duration", 0.2))
            return self._action_result(da.success, da.error, da.replay_node_id)
        elif action == "click":
            da = ctrl.click(task.get("x", 0), task.get("y", 0), task.get("button", "left"))
            return self._action_result(da.success, da.error, da.replay_node_id)
        elif action == "double_click":
            da = ctrl.double_click(task.get("x", 0), task.get("y", 0))
            return self._action_result(da.success, da.error, da.replay_node_id)
        elif action == "scroll":
            da = ctrl.scroll(task.get("clicks", 0), task.get("x"), task.get("y"))
            return self._action_result(da.success, da.error, da.replay_node_id)
        elif action == "drag":
            da = ctrl.drag(
                task.get("start_x", 0), task.get("start_y", 0),
                task.get("end_x", 0), task.get("end_y", 0),
                task.get("duration", 0.3),
            )
            return self._action_result(da.success, da.error, da.replay_node_id)

        # Keyboard actions
        elif action == "type_text":
            da = ctrl.type_text(task.get("text", ""), task.get("interval", 0.05))
            return self._action_result(da.success, da.error, da.replay_node_id)
        elif action == "press_key":
            da = ctrl.press_key(task.get("key", ""))
            return self._action_result(da.success, da.error, da.replay_node_id)
        elif action == "hotkey":
            keys = task.get("keys", [])
            da = ctrl.hotkey(*keys) if isinstance(keys, list) else ctrl.hotkey(keys)
            return self._action_result(da.success, da.error, da.replay_node_id)

        # Screen capture
        elif action == "capture_screen":
            cr = screen.capture_screen()
            return self._action_result(
                True, "",
                cr.replay_node_id,
                output=f"Captured screen: {cr.artifact_id} ({cr.width}x{cr.height})",
            )
        elif action == "capture_window":
            cr = screen.capture_window(task.get("window_title"))
            return self._action_result(
                True, "",
                cr.replay_node_id,
                output=f"Captured window: {cr.artifact_id} ({cr.width}x{cr.height})",
            )
        elif action == "capture_region":
            cr = screen.capture_region(
                task.get("x", 0), task.get("y", 0),
                task.get("width", 100), task.get("height", 100),
            )
            return self._action_result(
                True, "",
                cr.replay_node_id,
                output=f"Captured region: {cr.artifact_id} ({cr.width}x{cr.height})",
            )

        # Window actions
        elif action == "window_focus":
            wa = win.focus(task.get("window_title", ""))
            return self._action_result(wa.success, wa.error, wa.replay_node_id)
        elif action == "window_minimize":
            wa = win.minimize(task.get("window_title", ""))
            return self._action_result(wa.success, wa.error, wa.replay_node_id)
        elif action == "window_maximize":
            wa = win.maximize(task.get("window_title", ""))
            return self._action_result(wa.success, wa.error, wa.replay_node_id)
        elif action == "window_restore":
            wa = win.restore(task.get("window_title", ""))
            return self._action_result(wa.success, wa.error, wa.replay_node_id)
        elif action == "window_close":
            wa = win.close(task.get("window_title", ""))
            return self._action_result(wa.success, wa.error, wa.replay_node_id)

        else:
            return {"success": False, "error": f"Unknown desktop action: {action}", "output": ""}

    def _action_result(self, success: bool, error: str, replay_node_id: str,
                       output: str = "") -> dict:
        return {
            "success": success,
            "error": error,
            "output": output,
            "replay_node_id": replay_node_id,
        }


desktop_provider = DesktopProvider()
