"""
Module: core.workspace.desktop_state
Real desktop state snapshot - screen, windows, processes, browser tabs.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging
import pyautogui

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    title: str = ""
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    isMinimized: bool = False
    isMaximized: bool = False
    isActive: bool = False


@dataclass
class BrowserTabInfo:
    title: str = ""
    url: str = ""
    index: int = 0


@dataclass
class ProcessInfo:
    name: str = ""
    pid: int = 0
    status: str = ""


@dataclass
class DesktopSnapshot:
    active_window: WindowInfo | None = None
    windows: list[WindowInfo] = field(default_factory=list)
    browser: Any = None
    processes: list[ProcessInfo] = field(default_factory=list)
    screen_width: int = 0
    screen_height: int = 0
    mouse_x: int = 0
    mouse_y: int = 0


class _BrowserTabs:
    def __init__(self) -> None:
        self.tabs: list[BrowserTabInfo] = []


class DesktopState:
    def __init__(self) -> None:
        logger.info("DesktopState initialized")

    async def snapshot(self) -> DesktopSnapshot:
        try:
            import pygetwindow as gw
            import psutil

            screen_w, screen_h = pyautogui.size()
            mx, my = pyautogui.position()

            windows = []
            active_win = None
            for w in gw.getAllWindows():
                if not w.title.strip():
                    continue
                info = WindowInfo(
                    title=w.title,
                    left=w.left,
                    top=w.top,
                    width=w.width,
                    height=w.height,
                    isMinimized=w.isMinimized,
                    isMaximized=w.isMaximized,
                    isActive=w.isActive,
                )
                windows.append(info)
                if w.isActive:
                    active_win = info

            processes = []
            for proc in psutil.process_iter(["name", "pid", "status"]):
                try:
                    info = proc.info
                    processes.append(ProcessInfo(
                        name=info.get("name", ""),
                        pid=info.get("pid", 0),
                        status=str(info.get("status", "")),
                    ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            return DesktopSnapshot(
                active_window=active_win,
                windows=windows,
                browser=_BrowserTabs(),
                processes=processes,
                screen_width=screen_w,
                screen_height=screen_h,
                mouse_x=mx,
                mouse_y=my,
            )
        except Exception as e:
            logger.error("snapshot failed: %s", e)
            return DesktopSnapshot()
