from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.widgets import Label, Static, Button, DataTable
from jarvis_tui.app.screens.base_screen import JarvisScreen

logger = logging.getLogger(__name__)

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
            if isinstance(settings, dict):
                for k, v in settings.items():
                    table.add_row(k, str(v))
            elif isinstance(settings, list):
                for s in settings:
                    table.add_row(s.get("key", "N/A"), str(s.get("value", "N/A")))
            else:
                table.add_row("(unexpected format)", str(type(settings)))
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)
            table.add_row("(error loading settings)", str(e))
            self.app.notify(f"Could not load settings: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            table = self.query_one("#settings-table", DataTable)
            saved = 0
            errors = 0
            for row in table.rows:
                cells = row._cells
                if len(cells) >= 2:
                    k, v = cells[0], cells[1]
                    if k.startswith("("):
                        continue
                    try:
                        self.app.jarvis_client.update_setting(k, v)
                        saved += 1
                    except Exception as e:
                        logger.warning("Failed to save setting %s: %s", k, e)
                        errors += 1
                        self.app.notify(f"Failed to save {k}", severity="error")
            if errors:
                self.app.notify(f"Saved {saved} setting(s), {errors} failed", severity="warning")
            else:
                self.app.notify(f"Saved {saved} setting(s)", severity="information")
