from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal

class ConfirmGate(Widget):
    """
    Confirmation gate for critical actions.
    """
    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Label("[bold red]CRITICAL ACTION REQUIRED[/bold red]")
            yield Label("Forge wants to overwrite 'main.py'. Proceed?")
            with Horizontal():
                yield Button("APPROVE", variant="success", id="approve")
                yield Button("DENY", variant="error", id="deny")
                yield Button("EDIT", id="edit")

    def on_mount(self) -> None:
        self.display = False
