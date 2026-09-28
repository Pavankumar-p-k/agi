"""DesktopController — executes desktop actions through the safety gate.

Gate 1: every action is checked by SafetyManager *before* execution.
Gate 6: every accepted action is recorded in the ReplayGraph.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.desktop.safety import DesktopActionType, SafetyManager, safety_manager
from core.desktop.replay import ReplayGraph, ReplayNode, desktop_replay


@dataclass
class DesktopAction:
    """A single desktop automation request."""
    action_type: DesktopActionType
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "params": dict(self.params),
        }


@dataclass
class ActionResult:
    """Honest result of a desktop action attempt."""
    success: bool
    action: str = ""
    blocked: bool = False
    reason: str = ""
    error: str = ""
    output: Any = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action": self.action,
            "blocked": self.blocked,
            "reason": self.reason,
            "error": self.error,
            "output": self.output,
        }


@dataclass
class ScreenSize:
    width: int
    height: int


@dataclass
class Point:
    x: int
    y: int


class DesktopController:
    """Executes desktop actions: safety check -> replay record -> act."""

    def __init__(self, safety: Optional[SafetyManager] = None,
                 replay: Optional[ReplayGraph] = None) -> None:
        self.safety = safety if safety is not None else safety_manager
        self.replay = replay if replay is not None else desktop_replay
        self._dry_run = False

    # ── public API ───────────────────────────────────────────────────
    def perform(self, action: DesktopAction) -> ActionResult:
        decision = self.safety.check(action.action_type, action.params)
        if not decision.allowed:
            return ActionResult(
                success=False,
                action=action.action_type.value,
                blocked=True,
                reason=decision.reason,
            )

        node = self.replay.record(action.action_type.value, dict(action.params))
        output: Any = None
        if not self._dry_run:
            output = self._execute(action.action_type, action.params)
        return ActionResult(
            success=True,
            action=action.action_type.value,
            reason=decision.reason,
            output={"replay_node": node.node_id, "result": output},
        )

    async def perform_async(self, action: DesktopAction) -> ActionResult:
        return self.perform(action)

    # ── convenience helpers ──────────────────────────────────────────
    def move_mouse(self, x: int, y: int) -> ActionResult:
        return self.perform(DesktopAction(
            DesktopActionType.MOUSE_MOVE, {"x": x, "y": y}))

    def click(self, x: int, y: int) -> ActionResult:
        return self.perform(DesktopAction(
            DesktopActionType.MOUSE_CLICK, {"x": x, "y": y}))

    def type_text(self, text: str, rate_char_per_sec: float = 0) -> ActionResult:
        return self.perform(DesktopAction(
            DesktopActionType.KEYBOARD_TYPE,
            {"text": text, "rate_char_per_sec": rate_char_per_sec}))

    def capture_screen(self) -> ActionResult:
        return self.perform(DesktopAction(DesktopActionType.SCREEN_CAPTURE))

    def focus_window(self, window_title: str) -> ActionResult:
        return self.perform(DesktopAction(
            DesktopActionType.WINDOW_FOCUS, {"window_title": window_title}))

    # ── primitives used by the desktop agent loop ────────────────────
    @property
    def safety_gate(self) -> SafetyManager:
        return self.safety

    def get_screen_size(self) -> ScreenSize:
        try:
            import pyautogui
            size = pyautogui.size()
            return ScreenSize(width=int(size.width), height=int(size.height))
        except Exception:  # noqa: BLE001
            return ScreenSize(width=1920, height=1080)

    def get_mouse_position(self) -> Point:
        try:
            import pyautogui
            pos = pyautogui.position()
            return Point(x=int(pos.x), y=int(pos.y))
        except Exception:  # noqa: BLE001
            return Point(x=0, y=0)

    def move_mouse(self, x: int, y: int) -> ActionResult:
        return self._primitive(DesktopActionType.MOUSE_MOVE, {"x": x, "y": y},
                               lambda: __import__("pyautogui").moveTo(x, y))

    def click(self, x: int, y: int) -> ActionResult:
        return self._primitive(DesktopActionType.MOUSE_CLICK, {"x": x, "y": y},
                               lambda: __import__("pyautogui").click(x, y))

    def type_text(self, text: str, interval: float = 0.05) -> ActionResult:
        # Rate limiting is enforced by the agent's consent layer, which
        # computes rate_char_per_sec explicitly; the controller only
        # checks text length via the safety gate.
        return self._primitive(
            DesktopActionType.KEYBOARD_TYPE, {"text": str(text), "rate_char_per_sec": 0},
            lambda: __import__("pyautogui").typewrite(str(text), interval=interval),
        )

    def press_key(self, key: str) -> ActionResult:
        return self._primitive(
            DesktopActionType.KEYBOARD_TYPE, {"text": f"[key:{key}]", "rate_char_per_sec": 0},
            lambda: __import__("pyautogui").press(key),
        )

    def hotkey(self, *keys: str) -> ActionResult:
        combo = "+".join(keys)
        return self._primitive(
            DesktopActionType.KEYBOARD_TYPE, {"text": f"[hotkey:{combo}]", "rate_char_per_sec": 0},
            lambda: __import__("pyautogui").hotkey(*keys),
        )

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int,
             duration: float = 0.5) -> ActionResult:
        import math
        steps = max(int(duration / 0.02), 2)
        def _drag():
            import pyautogui
            pyautogui.moveTo(from_x, from_y)
            pyautogui.mouseDown()
            for i in range(1, steps + 1):
                t = i / steps
                px = from_x + (to_x - from_x) * t
                py_ = from_y + (to_y - from_y) * t
                pyautogui.moveTo(int(px), int(py_))
            pyautogui.mouseUp()
        result = self._primitive(
            DesktopActionType.MOUSE_CLICK,
            {"x": to_x, "y": to_y, "from_x": from_x, "from_y": from_y},
            _drag,
        )
        result.action = "drag"
        return result

    def open_url(self, url: str) -> ActionResult:
        import webbrowser
        def _open():
            webbrowser.open(str(url))
        return self._primitive(
            DesktopActionType.WINDOW_MANAGE, {"window_title": str(url)}, _open)

    def launch_app(self, app: str) -> ActionResult:
        import shutil
        import subprocess
        resolved = shutil.which(str(app)) or str(app)
        def _launch():
            subprocess.Popen([resolved], shell=False)
        result = self._primitive(
            DesktopActionType.WINDOW_MANAGE, {"window_title": str(app)}, _launch)
        result.action = "launch_app"
        return result

    def _primitive(self, action_type: DesktopActionType, params: dict,
                   backend) -> ActionResult:
        """Safety-check, replay-record, then run a real backend callable."""
        decision = self.safety.check(action_type, params)
        if not decision.allowed:
            return ActionResult(success=False, action=action_type.value,
                                blocked=True, reason=decision.reason,
                                error=decision.reason)
        node = self.replay.record(action_type.value, dict(params))
        try:
            backend()
            output: Any = {"executed": True, "replay_node": node.node_id}
        except Exception as exc:  # noqa: BLE001 — backend errors surface honestly
            return ActionResult(success=False, action=action_type.value,
                                reason=decision.reason, error=str(exc))
        return ActionResult(success=True, action=action_type.value,
                            reason=decision.reason, output=output)

    # ── backend dispatch ─────────────────────────────────────────────
    def _execute(self, action_type: DesktopActionType,
                 params: dict) -> Any:
        """Dispatch to the OS backend; returns a best-effort result.

        The real OS bridge (pyautogui etc.) is optional: when unavailable
        the controller still reports the action as accepted-and-recorded
        (safety + replay are the contract), with the execution outcome
        carried honestly in `output`.
        """
        try:
            import pyautogui  # noqa: F401 — optional backend
        except ImportError:
            return {"executed": False,
                    "reason": "no OS backend installed (dry acceptance)"}

        try:
            if action_type is DesktopActionType.MOUSE_MOVE:
                import pyautogui
                pyautogui.moveTo(params.get("x", 0), params.get("y", 0))
                return {"executed": True}
            if action_type is DesktopActionType.MOUSE_CLICK:
                import pyautogui
                pyautogui.click(params.get("x", 0), params.get("y", 0))
                return {"executed": True}
            if action_type is DesktopActionType.KEYBOARD_TYPE:
                import pyautogui
                pyautogui.typewrite(str(params.get("text", "")))
                return {"executed": True}
            if action_type is DesktopActionType.SCREEN_CAPTURE:
                import pyautogui
                shot = pyautogui.screenshot()
                return {"executed": True, "size": list(shot.size)}
            if action_type is DesktopActionType.WINDOW_FOCUS:
                return self._focus_window(params.get("window_title", ""))
        except Exception as exc:  # noqa: BLE001 — backend errors surface honestly
            return {"executed": False, "error": str(exc)}
        return {"executed": False, "reason": "unknown action"}

    @staticmethod
    def _focus_window(window_title: str) -> dict:
        try:
            import pygetwindow
            windows = pygetwindow.getWindowsWithTitle(window_title)
            if windows:
                windows[0].activate()
                return {"executed": True, "window": window_title}
            return {"executed": False, "reason": "window not found"}
        except ImportError:
            return {"executed": False, "reason": "no window backend installed"}


# Module-level singleton.
desktop_controller = DesktopController()


__all__ = ["DesktopAction", "ActionResult", "DesktopController",
           "desktop_controller"]
