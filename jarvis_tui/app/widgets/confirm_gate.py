# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label


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
