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
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static


class WhisperChannel(Widget):
    """
    Internal monologue/agent-to-agent channel (Ctrl+W toggle).
    """
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold magenta]AGENT WHISPER CHANNEL[/bold magenta]")
            yield Static("NEXUS -> FORGE: 'I found the relevant API keys.'", classes="whisper")
            yield Static("FORGE -> NEXUS: 'Proceeding with code generation.'", classes="whisper")
            yield Static("SYSTEM: 'Optimizing token usage for session #42'", classes="whisper")

    def on_mount(self) -> None:
        self.display = False
        self.styles.width = 40
        self.styles.dock = "right"
        self.styles.background = "#2a1a2a"
        self.styles.border_left = ("solid", "#4a2a4a")
        self.styles.padding = 1

    def toggle(self) -> None:
        self.display = not self.display
