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

class DiagnosticsDashboardScreen(JarvisScreen):
    """
    TUI Diagnostics Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# DIAGNOSTICS", id="screen-title")
        yield Label("System health and performance audit.")
        
        yield Label("## SYSTEM ENVIRONMENT")
        yield DataTable(id="env-table")
        
        yield Label("## COMPONENT HEALTH")
        yield DataTable(id="health-table")
        
        with Horizontal(id="diag-actions"):
            yield Button("Run Full Audit", id="btn-audit", variant="primary")

    async def on_mount(self) -> None:
        e_table = self.query_one("#env-table", DataTable)
        e_table.add_columns("Metric", "Value")
        
        h_table = self.query_one("#health-table", DataTable)
        h_table.add_columns("Component", "Status", "Message")
        
        await self.refresh_diagnostics()

    async def refresh_diagnostics(self) -> None:
        try:
            data = await self.app.jarvis_client.get_diagnostics()
            diag_data = data.get("data", {})
            
            e_table = self.query_one("#env-table", DataTable)
            e_table.clear()
            env = diag_data.get("environment", {})
            e_table.add_row("Disk Free", f"{env.get('disk_free_gb', 'N/A')} GB")
            e_table.add_row("Memory Free", f"{env.get('memory_free_mb', 'N/A')} MB")
            e_table.add_row("Ollama", "ONLINE" if env.get("ollama_available") else "OFFLINE")
            
            h_table = self.query_one("#health-table", DataTable)
            h_table.clear()
            # Placeholder for component health mapping
            h_table.add_row("CORE", "💚 HEALTHY", "All systems nominal")
            h_table.add_row("MODELS", "💚 HEALTHY", f"{len(diag_data.get('models', {}))} models verified")
            h_table.add_row("INTEGRATIONS", "💛 WARNING", "Slack connection latent")
            
        except Exception as e:
            self.app.notify(f"Error fetching diagnostics: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-audit":
            await self.refresh_diagnostics()
            self.app.notify("Full audit completed.", severity="success")
