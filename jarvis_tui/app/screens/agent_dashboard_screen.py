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

class AgentDashboardScreen(JarvisScreen):
    """
    TUI Agent Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# AGENT DASHBOARD", id="screen-title")
        yield Label("Monitor and deploy autonomous agents.")
        
        yield DataTable(id="agents-table")
        
        with Horizontal(id="agent-actions"):
            yield Button("Refresh", id="btn-refresh", variant="primary")
            yield Button("Run Task", id="btn-run")

    async def on_mount(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.add_columns("Name", "Modes", "Description")
        table.cursor_type = "row"
        await self.refresh_agents()

    async def refresh_agents(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.clear()
        try:
            data = await self.app.jarvis_client.get_agents()
            agents = data.get("agents", [])
            for a in agents:
                table.add_row(
                    a.get("name", "N/A"),
                    ", ".join(a.get("modes", [])),
                    a.get("description", "")
                )
        except Exception as e:
            self.app.notify(f"Error fetching agents: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            await self.refresh_agents()
        else:
            self.app.notify("Action not yet implemented", severity="warning")
