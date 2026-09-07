"""
Module: core.workspace.window_detector
Real window detection using pygetwindow.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DetectedWindow:
    title: str = ""
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    isMinimized: bool = False
    isMaximized: bool = False
    isActive: bool = False


class WindowDetector:
    def __init__(self) -> None:
        logger.info("WindowDetector initialized")

    def detect_all(self) -> list[DetectedWindow]:
        try:
            import pygetwindow as gw
            windows = []
            for w in gw.getAllWindows():
                if not w.title.strip():
                    continue
                windows.append(DetectedWindow(
                    title=w.title,
                    left=w.left,
                    top=w.top,
                    width=w.width,
                    height=w.height,
                    isMinimized=w.isMinimized,
                    isMaximized=w.isMaximized,
                    isActive=w.isActive,
                ))
            return windows
        except Exception as e:
            logger.error("detect_all failed: %s", e)
            return []

    def find_by_title(self, title: str) -> DetectedWindow | None:
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return None
            w = windows[0]
            return DetectedWindow(
                title=w.title,
                left=w.left,
                top=w.top,
                width=w.width,
                height=w.height,
                isMinimized=w.isMinimized,
                isMaximized=w.isMaximized,
                isActive=w.isActive,
            )
        except Exception as e:
            logger.error("find_by_title failed: %s", e)
            return None

    def get_active(self) -> DetectedWindow | None:
        try:
            import pygetwindow as gw
            w = gw.getActiveWindow()
            if w is None:
                return None
            return DetectedWindow(
                title=w.title,
                left=w.left,
                top=w.top,
                width=w.width,
                height=w.height,
                isMinimized=w.isMinimized,
                isMaximized=w.isMaximized,
                isActive=w.isActive,
            )
        except Exception as e:
            logger.error("get_active failed: %s", e)
            return None

    def snapshot(self) -> dict[str, Any]:
        all_wins = self.detect_all()
        active = self.get_active()
        return {
            "active_window": active.__dict__ if active else None,
            "windows": [w.__dict__ for w in all_wins],
            "total": len(all_wins),
        }
