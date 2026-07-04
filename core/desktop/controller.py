from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.desktop.replay import ReplayNode, desktop_replay
from core.desktop.safety import DesktopActionType, SafetyManager, safety_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DesktopAction:
    action_type: DesktopActionType
    success: bool
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    replay_node_id: str = ""

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "success": self.success,
            "error": self.error,
            "details": dict(self.details),
            "replay_node_id": self.replay_node_id,
        }


class DesktopController:
    def __init__(self, safety: SafetyManager | None = None) -> None:
        self._safety = safety or safety_manager
        self._pyautogui = None

    def _get_pyautogui(self):
        if self._pyautogui is None:
            import pyautogui
            pyautogui.FAILSAFE = True
            self._pyautogui = pyautogui
        return self._pyautogui

    # ── Mouse Primitives ──────────────────────────────────────────────────

    def move_mouse(self, x: int, y: int, duration: float = 0.2) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.MOUSE_MOVE, {"x": x, "y": y})
        if not decision.allowed:
            return self._reject(DesktopActionType.MOUSE_MOVE, decision.reason)
        try:
            self._get_pyautogui().moveTo(x, y, duration=duration)
            node = desktop_replay.record("move_mouse", {"x": x, "y": y, "duration": duration})
            return DesktopAction(
                action_type=DesktopActionType.MOUSE_MOVE,
                success=True,
                details={"x": x, "y": y},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.MOUSE_MOVE, str(e))

    def click(self, x: int, y: int, button: str = "left") -> DesktopAction:
        decision = self._safety.check(DesktopActionType.MOUSE_CLICK, {"x": x, "y": y, "button": button})
        if not decision.allowed:
            return self._reject(DesktopActionType.MOUSE_CLICK, decision.reason)
        try:
            self._get_pyautogui().click(x, y, button=button)
            node = desktop_replay.record("click", {"x": x, "y": y, "button": button})
            return DesktopAction(
                action_type=DesktopActionType.MOUSE_CLICK,
                success=True,
                details={"x": x, "y": y, "button": button},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.MOUSE_CLICK, str(e))

    def double_click(self, x: int, y: int) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.MOUSE_DOUBLE_CLICK, {"x": x, "y": y})
        if not decision.allowed:
            return self._reject(DesktopActionType.MOUSE_DOUBLE_CLICK, decision.reason)
        try:
            self._get_pyautogui().doubleClick(x, y)
            node = desktop_replay.record("double_click", {"x": x, "y": y})
            return DesktopAction(
                action_type=DesktopActionType.MOUSE_DOUBLE_CLICK,
                success=True,
                details={"x": x, "y": y},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.MOUSE_DOUBLE_CLICK, str(e))

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.MOUSE_SCROLL, {"clicks": clicks})
        if not decision.allowed:
            return self._reject(DesktopActionType.MOUSE_SCROLL, decision.reason)
        try:
            self._get_pyautogui().scroll(clicks, x=x, y=y)
            node = desktop_replay.record("scroll", {"clicks": clicks, "x": x, "y": y})
            return DesktopAction(
                action_type=DesktopActionType.MOUSE_SCROLL,
                success=True,
                details={"clicks": clicks},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.MOUSE_SCROLL, str(e))

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.3) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.MOUSE_DRAG, {"x": end_x, "y": end_y})
        if not decision.allowed:
            return self._reject(DesktopActionType.MOUSE_DRAG, decision.reason)
        try:
            p = self._get_pyautogui()
            p.moveTo(start_x, start_y)
            p.drag(end_x - start_x, end_y - start_y, duration=duration)
            node = desktop_replay.record("drag", {
                "start_x": start_x, "start_y": start_y,
                "end_x": end_x, "end_y": end_y,
            })
            return DesktopAction(
                action_type=DesktopActionType.MOUSE_DRAG,
                success=True,
                details={"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.MOUSE_DRAG, str(e))

    # ── Keyboard Primitives ───────────────────────────────────────────────

    def type_text(self, text: str, interval: float = 0.05) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.KEYBOARD_TYPE, {
            "text": text, "rate_char_per_sec": 1.0 / interval if interval > 0 else 0,
        })
        if not decision.allowed:
            return self._reject(DesktopActionType.KEYBOARD_TYPE, decision.reason)
        try:
            self._get_pyautogui().typewrite(text, interval=interval)
            node = desktop_replay.record("type_text", {"text_length": len(text)})
            return DesktopAction(
                action_type=DesktopActionType.KEYBOARD_TYPE,
                success=True,
                details={"text_length": len(text), "interval": interval},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.KEYBOARD_TYPE, str(e))

    def press_key(self, key: str) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.KEYBOARD_PRESS, {"key": key})
        if not decision.allowed:
            return self._reject(DesktopActionType.KEYBOARD_PRESS, decision.reason)
        try:
            self._get_pyautogui().press(key)
            node = desktop_replay.record("press_key", {"key": key})
            return DesktopAction(
                action_type=DesktopActionType.KEYBOARD_PRESS,
                success=True,
                details={"key": key},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.KEYBOARD_PRESS, str(e))

    def hotkey(self, *keys: str) -> DesktopAction:
        decision = self._safety.check(DesktopActionType.KEYBOARD_HOTKEY, {"keys": list(keys)})
        if not decision.allowed:
            return self._reject(DesktopActionType.KEYBOARD_HOTKEY, decision.reason)
        try:
            self._get_pyautogui().hotkey(*keys)
            node = desktop_replay.record("hotkey", {"keys": list(keys)})
            return DesktopAction(
                action_type=DesktopActionType.KEYBOARD_HOTKEY,
                success=True,
                details={"keys": list(keys)},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.KEYBOARD_HOTKEY, str(e))

    # ── App & URL Launchers ──────────────────────────────────────────────

    def open_url(self, url: str) -> DesktopAction:
        """Open a URL in the default browser."""
        try:
            import webbrowser
            webbrowser.open(url)
            node = desktop_replay.record("open_url", {"url": url})
            return DesktopAction(
                action_type=DesktopActionType.MOUSE_CLICK,
                success=True,
                details={"url": url},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.MOUSE_CLICK, str(e))

    def launch_app(self, app_name: str) -> DesktopAction:
        """Launch a system application."""
        import shutil
        import subprocess
        import sys as _sys
        exe = shutil.which(app_name)
        if not exe:
            candidates = {
                "notepad": "notepad.exe", "calculator": "calc.exe",
                "cmd": "cmd.exe", "terminal": "cmd.exe",
                "explorer": "explorer.exe", "chrome": "chrome.exe",
                "firefox": "firefox.exe", "code": "code.cmd",
            }
            exe = candidates.get(app_name.lower(), app_name)
        try:
            kwargs = {"shell": True} if _sys.platform == "win32" else {}
            subprocess.Popen([exe] if not kwargs else exe, **kwargs)
            node = desktop_replay.record("launch_app", {"app": app_name})
            return DesktopAction(
                action_type=DesktopActionType.KEYBOARD_HOTKEY,
                success=True,
                details={"app": app_name},
                replay_node_id=node.node_id,
            )
        except Exception as e:
            return self._error(DesktopActionType.KEYBOARD_HOTKEY, str(e))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _reject(self, action_type: DesktopActionType, reason: str) -> DesktopAction:
        logger.warning("[DesktopController] Blocked by Safety: %s — %s", action_type.value, reason)
        return DesktopAction(action_type=action_type, success=False, error=reason)

    def _error(self, action_type: DesktopActionType, error: str) -> DesktopAction:
        logger.warning("[DesktopController] Error: %s — %s", action_type.value, error)
        return DesktopAction(action_type=action_type, success=False, error=error)


desktop_controller = DesktopController()
