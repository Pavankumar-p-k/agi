"""BrowserContextAwareness — passive browser state detection.

Read-only: detects whether a browser process is running and exposes a
best-effort active state snapshot. Never drives the browser.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BrowserState:
    has_browser: bool = False
    url: str = ""
    title: str = ""
    tab_count: int = 0
    browser_name: str = ""
    metadata: dict = field(default_factory=dict)


class BrowserContextAwareness:
    """Detects running browsers via process inspection (no control)."""

    BROWSER_PROCESSES = ("chrome", "msedge", "firefox", "brave", "opera")

    def __init__(self) -> None:
        self._monitor = None

    def _monitor_for(self):
        if self._monitor is None:
            from core.workspace.process_monitor import ProcessMonitor
            self._monitor = ProcessMonitor()
        return self._monitor

    async def get_active_state(self) -> BrowserState:
        monitor = self._monitor_for()
        state = BrowserState()
        for browser in self.BROWSER_PROCESSES:
            procs = monitor.find_by_name(browser)
            if procs:
                state.has_browser = True
                state.browser_name = browser
                state.tab_count = len(procs)
                break
        return state

    async def is_browser_active(self) -> bool:
        state = await self.get_active_state()
        return state.has_browser


__all__ = ["BrowserContextAwareness", "BrowserState"]
