from __future__ import annotations

from dataclasses import dataclass, field

from core.workspace.window_detector import WindowDetector, WindowInfo
from core.workspace.browser_context import BrowserContextAwareness, BrowserState
from core.workspace.clipboard_manager import ClipboardManager
from core.workspace.process_monitor import ProcessMonitor, ProcessInfo


@dataclass
class DesktopSnapshot:
    active_window: WindowInfo | None
    windows: list[WindowInfo]
    browser: BrowserState
    clipboard_text: str
    processes: list[ProcessInfo]
    system_stats: dict


class DesktopState:
    def __init__(self) -> None:
        self.window_detector = WindowDetector()
        self.browser_context = BrowserContextAwareness()
        self.clipboard = ClipboardManager()
        self.process_monitor = ProcessMonitor()

    async def snapshot(self, session_id: str = "") -> DesktopSnapshot:
        return DesktopSnapshot(
            active_window=self.window_detector.get_active_window(),
            windows=self.window_detector.list_windows(),
            browser=await self.browser_context.get_active_state(session_id=session_id),
            clipboard_text=self.clipboard.get_text(),
            processes=self.process_monitor.list_processes(),
            system_stats=self.process_monitor.get_system_stats(),
        )
