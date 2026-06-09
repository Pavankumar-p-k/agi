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

import difflib

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static


class DiffPane(Widget):
    """
    Side-by-side file diff view with line-level highlighting.
    """
    def __init__(self, old_content: str, new_content: str, filename: str, **kwargs):
        super().__init__(**kwargs)
        self.old_content = old_content
        self.new_content = new_content
        self.filename = filename

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Vertical(Static(f"[bold red]OLD: {self.filename}[/bold red]"), id="diff-old")
            yield Vertical(Static(f"[bold green]NEW: {self.filename}[/bold green]"), id="diff-new")

    def on_mount(self) -> None:
        self.display = False
        self.render_diff()

    def render_diff(self) -> None:
        old_side = self.query_one("#diff-old", Vertical)
        new_side = self.query_one("#diff-new", Vertical)

        diff = list(difflib.ndiff(self.old_content.splitlines(), self.new_content.splitlines()))

        for line in diff:
            if line.startswith("- "):
                old_side.mount(Static(Text(line[2:], style="red")))
                new_side.mount(Static("")) # Empty line for alignment
            elif line.startswith("+ "):
                old_side.mount(Static("")) # Empty line for alignment
                new_side.mount(Static(Text(line[2:], style="green")))
            elif line.startswith("  "):
                old_side.mount(Static(Text(line[2:], style="dim")))
                new_side.mount(Static(Text(line[2:], style="dim")))
