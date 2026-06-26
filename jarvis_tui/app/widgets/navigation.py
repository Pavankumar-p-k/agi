from __future__ import annotations

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

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button


class Navigation(Widget):
    """
    Unified navigation menu for the JARVIS TUI.
    """
    class Selected(Message):
        """Sent when a navigation item is selected."""
        def __init__(self, screen_name: str) -> None:
            self.screen_name = screen_name
            super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="nav-container"):
            yield Button("Home", id="nav-home", variant="primary")
            yield Button("Chat", id="nav-chat")
            yield Button("Voice", id="nav-voice")
            yield Button("Models", id="nav-models")
            yield Button("Agents", id="nav-agents")
            yield Button("Activity", id="nav-activity")
            yield Button("Automation", id="nav-automation")
            yield Button("Memory", id="nav-memory")
            yield Button("Skills", id="nav-skills")
            yield Button("Plugins", id="nav-plugins")
            yield Button("Integrations", id="nav-integrations")
            yield Button("Projects", id="nav-projects")
            yield Button("Diagnostics", id="nav-diagnostics")
            yield Button("Settings", id="nav-settings")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        screen_name = event.button.id.replace("nav-", "")
        self.post_message(self.Selected(screen_name))
        
        # Update active button styling
        for btn in self.query(Button):
            btn.variant = "default"
        event.button.variant = "primary"
