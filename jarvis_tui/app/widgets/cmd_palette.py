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
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, Static


class CommandPalette(Widget):
    """
    Command palette overlay with fuzzy search and multi-trigger support.
    """
    COMMANDS = [
        "/research   → spin NEXUS deep search session",
        "/codegen    → spawn FORGE with task description",
        "/model      → switch model mid-session",
        "/theme      → cycle visual themes",
        "/agent      → spawn / kill / inspect agent",
        "/vault      → open encrypted memory vault",
        "/export     → save session to markdown/JSON",
        "/clear      → nuke context with confirmation",
        "/exit       → terminate session",
        "/replay     → temporal replay mode",
    ]

    THEMES = ["anthropic", "midnight", "solarized"]

    AGENTS = [
        "@nexus      → research and retrieval specialist",
        "@forge      → code generation and refactoring",
        "@scout      → background monitor and web search",
        "@oracle     → planning and orchestration",
    ]

    TOOLS = [
        "!web_search  → search the internet",
        "!read_file   → read file contents",
        "!write_file  → write content to file",
        "!ls          → list directory contents",
    ]

    def compose(self) -> ComposeResult:
        yield Static("▒" * 200, id="palette-blur") # Simulated blur background
        with Vertical(id="palette-container"):
            yield Input(placeholder="Type / @ ! or #...", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        self.display = False
        self.update_list("/")

    def toggle(self, trigger: str = "/") -> None:
        self.display = not self.display
        if self.display:
            inp = self.query_one("#palette-input", Input)
            inp.value = trigger
            inp.focus()
            self.update_list(trigger)

    def update_list(self, filter_text: str) -> None:
        lst = self.query_one("#palette-list", ListView)
        lst.clear()

        source = self.COMMANDS
        if filter_text.startswith("@"): source = self.AGENTS
        elif filter_text.startswith("!"): source = self.TOOLS
        elif filter_text.startswith("#"): source = ["#bookmark → tag current message"]

        for item in source:
            if filter_text.lower() in item.lower():
                lst.append(ListItem(Label(item)))

    def on_input_changed(self, event: Input.Changed) -> None:
        self.update_list(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        cmd_text = event.item.query_one(Label).renderable
        try:
            toast_rack = self.screen.query_one("#toast-rack")
        except Exception:
            toast_rack = None

        if "/theme" in cmd_text:
            idx = getattr(self.app, "_theme_idx", 0)
            next_idx = (idx + 1) % len(self.THEMES)
            self.app.switch_theme(self.THEMES[next_idx])
            self.app._theme_idx = next_idx
        elif "/replay" in cmd_text:
            from jarvis_tui.app.screens.replay_screen import ReplayScreen
            self.app.push_screen(ReplayScreen())
        elif "/exit" in cmd_text:
            self.app.exit()
        elif cmd_text.startswith("@"):
            if toast_rack:
                toast_rack.show_toast(f"Routing to {cmd_text.split()[0]}", severity="info")
        elif cmd_text.startswith("!"):
            if toast_rack:
                toast_rack.show_toast(f"Executing tool {cmd_text.split()[0]}", severity="success")

        self.toggle()
