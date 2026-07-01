from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.desktop.replay import desktop_replay
from core.desktop.safety import DesktopActionType, SafetyManager, safety_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowActionResult:
    action: str
    window_title: str
    success: bool
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    replay_node_id: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "window_title": self.window_title,
            "success": self.success,
            "error": self.error,
            "details": dict(self.details),
            "replay_node_id": self.replay_node_id,
        }


class WindowController:
    def __init__(self, safety: SafetyManager | None = None) -> None:
        self._safety = safety or safety_manager

    def focus(self, window_title: str) -> WindowActionResult:
        import pygetwindow as gw
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return WindowActionResult("focus", window_title, False, f"No window: {window_title}")
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            node = desktop_replay.record("window_focus", {"window_title": window_title})
            return WindowActionResult(
                "focus", window_title, True,
                replay_node_id=node.node_id,
                details={"title": win.title},
            )
        except Exception as e:
            return WindowActionResult("focus", window_title, False, str(e))

    def minimize(self, window_title: str) -> WindowActionResult:
        import pygetwindow as gw
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return WindowActionResult("minimize", window_title, False, f"No window: {window_title}")
            win = windows[0]
            win.minimize()
            node = desktop_replay.record("window_minimize", {"window_title": window_title})
            return WindowActionResult("minimize", window_title, True, replay_node_id=node.node_id)
        except Exception as e:
            return WindowActionResult("minimize", window_title, False, str(e))

    def maximize(self, window_title: str) -> WindowActionResult:
        import pygetwindow as gw
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return WindowActionResult("maximize", window_title, False, f"No window: {window_title}")
            win = windows[0]
            win.maximize()
            node = desktop_replay.record("window_maximize", {"window_title": window_title})
            return WindowActionResult("maximize", window_title, True, replay_node_id=node.node_id)
        except Exception as e:
            return WindowActionResult("maximize", window_title, False, str(e))

    def restore(self, window_title: str) -> WindowActionResult:
        import pygetwindow as gw
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return WindowActionResult("restore", window_title, False, f"No window: {window_title}")
            win = windows[0]
            win.restore()
            node = desktop_replay.record("window_restore", {"window_title": window_title})
            return WindowActionResult("restore", window_title, True, replay_node_id=node.node_id)
        except Exception as e:
            return WindowActionResult("restore", window_title, False, str(e))

    def close(self, window_title: str) -> WindowActionResult:
        import pygetwindow as gw
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                return WindowActionResult("close", window_title, False, f"No window: {window_title}")
            win = windows[0]
            win.close()
            node = desktop_replay.record("window_close", {"window_title": window_title})
            return WindowActionResult("close", window_title, True, replay_node_id=node.node_id)
        except Exception as e:
            return WindowActionResult("close", window_title, False, str(e))


window_controller = WindowController()
