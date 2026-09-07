"""
Module: core.desktop.window
Real window management using pygetwindow.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging
import pygetwindow as gw

logger = logging.getLogger(__name__)


@dataclass
class WindowActionResult:
    success: bool = False
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class WindowController:
    def __init__(self) -> None:
        logger.info("WindowController initialized")

    def list_windows(self) -> list[dict[str, Any]]:
        try:
            windows = gw.getAllWindows()
            return [
                {
                    "title": w.title,
                    "left": w.left,
                    "top": w.top,
                    "width": w.width,
                    "height": w.height,
                    "isMinimized": w.isMinimized,
                    "isMaximized": w.isMaximized,
                    "isActive": w.isActive,
                }
                for w in windows
                if w.title.strip()
            ]
        except Exception as e:
            logger.error("list_windows failed: %s", e)
            return []

    def focus(self, title: str) -> WindowActionResult:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return WindowActionResult(error=f"No window found: {title}")
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            return WindowActionResult(
                success=True,
                details={"title": win.title, "action": "focus"},
            )
        except Exception as e:
            return WindowActionResult(error=str(e))

    def close(self, title: str) -> WindowActionResult:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return WindowActionResult(error=f"No window found: {title}")
            windows[0].close()
            return WindowActionResult(success=True, details={"title": title, "action": "close"})
        except Exception as e:
            return WindowActionResult(error=str(e))

    def minimize(self, title: str) -> WindowActionResult:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return WindowActionResult(error=f"No window found: {title}")
            windows[0].minimize()
            return WindowActionResult(success=True, details={"title": title, "action": "minimize"})
        except Exception as e:
            return WindowActionResult(error=str(e))

    def maximize(self, title: str) -> WindowActionResult:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return WindowActionResult(error=f"No window found: {title}")
            windows[0].maximize()
            return WindowActionResult(success=True, details={"title": title, "action": "maximize"})
        except Exception as e:
            return WindowActionResult(error=str(e))

    def resize(self, title: str, width: int, height: int) -> WindowActionResult:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return WindowActionResult(error=f"No window found: {title}")
            windows[0].resizeTo(width, height)
            return WindowActionResult(
                success=True,
                details={"title": title, "action": "resize", "width": width, "height": height},
            )
        except Exception as e:
            return WindowActionResult(error=str(e))

    def move(self, title: str, x: int, y: int) -> WindowActionResult:
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return WindowActionResult(error=f"No window found: {title}")
            windows[0].moveTo(x, y)
            return WindowActionResult(
                success=True,
                details={"title": title, "action": "move", "x": x, "y": y},
            )
        except Exception as e:
            return WindowActionResult(error=str(e))

    def get_active_window(self) -> dict[str, Any] | None:
        try:
            win = gw.getActiveWindow()
            if win is None:
                return None
            return {
                "title": win.title,
                "left": win.left,
                "top": win.top,
                "width": win.width,
                "height": win.height,
                "isMinimized": win.isMinimized,
                "isMaximized": win.isMaximized,
            }
        except Exception as e:
            logger.error("get_active_window failed: %s", e)
            return None

    def snapshot(self) -> dict[str, Any]:
        try:
            windows = self.list_windows()
            active = self.get_active_window()
            return {
                "active_window": active,
                "windows": windows,
                "total_windows": len(windows),
            }
        except Exception as e:
            return {"error": str(e)}


window_controller = WindowController()
