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
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Static, Button, DataTable
from jarvis_tui.app.screens.base_screen import JarvisScreen

class MemoryDashboardScreen(JarvisScreen):
    """
    TUI Memory Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# MEMORY DASHBOARD", id="screen-title")
        yield Label("Explore learned skills, failure memories and architectural patterns.")
        
        yield DataTable(id="memory-table")
        
        with Horizontal(id="memory-actions"):
            yield Button("Refresh", id="btn-refresh", variant="primary")
            yield Button("Prune Failure Memory", id="btn-prune")

    async def on_mount(self) -> None:
        table = self.query_one("#memory-table", DataTable)
        table.add_columns("Type", "Entries", "Description")
        table.add_row("FAILURE MEMORY", "12", "Automated repair logs and retry histories.")
        table.add_row("ARCHITECTURAL MEMORY", "5", "Codebase patterns and structural insights.")
        table.add_row("USER PREFERENCES", "24", "Learned habits and preferred models.")
        table.add_row("SKILL ACQUISITION", "8", "Newly learned tool usage patterns.")
