"""core.workspace — passive workspace awareness (Gate 8).

Awareness is deliberately separate from control: these modules observe
windows, clipboard, processes, browser state and the aggregate desktop
snapshot. Control actions live in core.desktop.
"""
from core.workspace.window_detector import WindowDetector
from core.workspace.browser_context import BrowserContextAwareness
from core.workspace.clipboard_manager import ClipboardManager
from core.workspace.process_monitor import ProcessMonitor
from core.workspace.desktop_state import DesktopState

__all__ = [
    "WindowDetector",
    "BrowserContextAwareness",
    "ClipboardManager",
    "ProcessMonitor",
    "DesktopState",
]
