"""DesktopState — one async snapshot of the whole workspace.

Composes the awareness modules (windows, browser, clipboard, processes,
system stats) into a single snapshot object. Awareness only — no
control actions (Gate 8 separation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DesktopSnapshot:
    active_window: Optional[str] = None
    windows: list = field(default_factory=list)
    browser: dict = field(default_factory=dict)
    clipboard_text: str = ""
    processes: list = field(default_factory=list)
    system_stats: dict = field(default_factory=dict)


class DesktopState:
    """Aggregated workspace awareness snapshot."""

    def __init__(self) -> None:
        from core.workspace.window_detector import WindowDetector
        from core.workspace.clipboard_manager import ClipboardManager
        from core.workspace.process_monitor import ProcessMonitor
        from core.workspace.browser_context import BrowserContextAwareness
        self.windows = WindowDetector()
        self.clipboard = ClipboardManager()
        self.processes = ProcessMonitor()
        self.browser = BrowserContextAwareness()

    async def snapshot(self) -> DesktopSnapshot:
        snap = DesktopSnapshot()

        active = self.windows.get_active_window()
        if active is not None:
            snap.active_window = getattr(active, "title", None)
        snap.windows = [w for w in self.windows.list_windows()]

        state = await self.browser.get_active_state()
        snap.browser = {
            "has_browser": state.has_browser,
            "browser_name": state.browser_name,
            "tab_count": state.tab_count,
        }

        snap.clipboard_text = self.clipboard.get_text()
        snap.processes = self.processes.list_processes()
        snap.system_stats = self.processes.get_system_stats()
        return snap


__all__ = ["DesktopState", "DesktopSnapshot"]
