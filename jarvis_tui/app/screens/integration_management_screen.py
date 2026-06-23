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

class IntegrationManagementScreen(JarvisScreen):
    """
    TUI Integration Management UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# INTEGRATIONS", id="screen-title")
        yield Label("Connect JARVIS to external platforms.")
        
        yield DataTable(id="integrations-table")
        
        with Horizontal(id="integration-actions"):
            yield Button("Refresh", id="btn-refresh", variant="primary")
            yield Button("Connect", id="btn-connect")
            yield Button("Disconnect", id="btn-disconnect")

    async def on_mount(self) -> None:
        table = self.query_one("#integrations-table", DataTable)
        table.add_columns("Name", "Status", "Health")
        table.cursor_type = "row"
        await self.refresh_integrations()

    async def refresh_integrations(self) -> None:
        table = self.query_one("#integrations-table", DataTable)
        table.clear()
        try:
            data = await self.app.jarvis_client.get_integrations()
            integrations = data.get("integrations", [])
            for i in integrations:
                connected = i.get("connected", False)
                status_str = "✅ CONNECTED" if connected else "❌ DISCONNECTED"
                health = i.get("status", {}).get("healthy", False)
                health_str = "💚 HEALTHY" if health else "💔 ERROR" if connected else "N/A"
                table.add_row(i.get("name", "N/A").upper(), status_str, health_str)
        except Exception as e:
            self.app.notify(f"Error fetching integrations: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            await self.refresh_integrations()
        else:
            self.app.notify("Action not yet implemented", severity="warning")
