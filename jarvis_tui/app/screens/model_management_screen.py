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

class ModelManagementScreen(JarvisScreen):
    """
    TUI Model Management UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# MODEL MANAGEMENT", id="screen-title")
        yield Label("Manage LLM providers and task assignments.")
        
        yield Label("## TASK ASSIGNMENTS")
        yield DataTable(id="groups-table")
        
        yield Label("## AVAILABLE MODELS")
        yield DataTable(id="models-table")

    async def on_mount(self) -> None:
        g_table = self.query_one("#groups-table", DataTable)
        g_table.add_columns("Task", "Assigned Model")
        
        m_table = self.query_one("#models-table", DataTable)
        m_table.add_columns("Name", "Provider", "Size")
        
        await self.refresh_data()

    async def refresh_data(self) -> None:
        try:
            groups_data = await self.app.jarvis_client.get_model_groups()
            g_table = self.query_one("#groups-table", DataTable)
            g_table.clear()
            for task, model in groups_data.get("groups", {}).items():
                g_table.add_row(task.upper(), model)
                
            models_data = await self.app.jarvis_client.get_models()
            m_table = self.query_one("#models-table", DataTable)
            m_table.clear()
            for m in models_data.get("models", []):
                size = m.get("size", 0)
                size_str = f"{size / (1024**3):.1f} GB" if size else "N/A"
                m_table.add_row(m.get("name", "Unknown"), m.get("provider", "unknown"), size_str)
        except Exception as e:
            self.app.notify(f"Error fetching model data: {e}", severity="error")
