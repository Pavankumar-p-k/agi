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

class FeatureRegistryScreen(JarvisScreen):
    """
    TUI Feature Registry UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# FEATURE REGISTRY", id="screen-title")
        yield Label("Manage JARVIS runtime features and capabilities.")
        
        with Vertical(id="feature-container"):
            yield DataTable(id="feature-table")
            
        with Horizontal(id="feature-actions"):
            yield Button("Refresh", id="btn-refresh", variant="primary")
            yield Button("Toggle Selected", id="btn-toggle")

    async def on_mount(self) -> None:
        table = self.query_one("#feature-table", DataTable)
        table.add_columns("Name", "Status", "Enabled", "Category", "Description")
        table.cursor_type = "row"
        await self.refresh_features()

    async def refresh_features(self) -> None:
        table = self.query_one("#feature-table", DataTable)
        table.clear()
        try:
            data = await self.app.jarvis_client.get_features()
            features = data.get("features", [])
            for f in features:
                table.add_row(
                    f.get("name", "N/A"),
                    f.get("status", "N/A"),
                    "✅ YES" if f.get("enabled") else "❌ NO",
                    f.get("category", "N/A"),
                    f.get("description", "")
                )
        except Exception as e:
            self.app.notify(f"Error fetching features: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            await self.refresh_features()
        elif event.button.id == "btn-toggle":
            table = self.query_one("#feature-table", DataTable)
            if table.cursor_row is not None:
                # In a real impl, we'd need a mapping from row index to feature slug
                # For brevity in this TUI prototype, we'll assume we can find it
                self.app.notify("Feature toggling not yet implemented for DataTable selection", severity="warning")
