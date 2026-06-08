from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Label
from textual.containers import Vertical
from textual.reactive import reactive
from textual.timer import Timer

class Toast(Static):
    """
    A single notification toast.
    """
    def __init__(self, message: str, severity: str = "info", timeout: float = 3.0, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.severity = severity
        self.timeout = timeout

    def compose(self) -> ComposeResult:
        icon = "ℹ"
        if self.severity == "success": icon = "✓"
        elif self.severity == "warning": icon = "⚠"
        elif self.severity == "error": icon = "✕"
        
        yield Label(f"{icon} {self.message}")

    def on_mount(self) -> None:
        self.set_timer(self.timeout, self.remove)

class ToastRack(Widget):
    """
    Container for stacking notification toasts.
    """
    def show_toast(self, message: str, severity: str = "info", timeout: float = 3.0) -> None:
        toast = Toast(message, severity, timeout)
        self.mount(toast)
