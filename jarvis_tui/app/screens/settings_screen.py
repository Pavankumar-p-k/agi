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
from textual.widgets import Label, Static, Button, DataTable
from jarvis_tui.app.screens.base_screen import JarvisScreen

class SettingsScreen(JarvisScreen):
    """
    TUI Settings UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# SETTINGS", id="screen-title")
        yield Label("Configure JARVIS platform preferences.")
        
        yield DataTable(id="settings-table")
        yield Button("Save Changes", id="btn-save", variant="primary")

    async def on_mount(self) -> None:
        table = self.query_one("#settings-table", DataTable)
        table.add_columns("Key", "Value")
        try:
            settings = await self.app.jarvis_client.get_settings()
            # Flatten settings for display
            if isinstance(settings, dict):
                for k, v in settings.items():
                    table.add_row(k, str(v))
            elif isinstance(settings, list):
                for s in settings:
                    table.add_row(s.get("key", "N/A"), str(s.get("value", "N/A")))
        except Exception:
            table.add_row("API_URL", self.app.jarvis_client.base_url)
            table.add_row("AUTO_REPAIR", "True")
            table.add_row("VOICE_ENABLED", "True")
