from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Static, Button, ProgressBar, DataTable
from jarvis_tui.app.screens.base_screen import JarvisScreen

logger = logging.getLogger(__name__)

class AutomationDashboardScreen(JarvisScreen):
    """
    TUI Automation Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# AUTOMATION DASHBOARD", id="screen-title")
        yield Label("Monitor active goals and autonomous workflows.")
        
        yield Label("## ACTIVE GOALS")
        yield DataTable(id="goals-table")
        
        yield Label("## EXECUTION LOG")
        yield Vertical(id="automation-log")
        
        with Horizontal(id="automation-actions"):
            yield Button("Refresh", id="btn-refresh", variant="primary")
            yield Button("Stop All", id="btn-stop", variant="error")
            yield Button("Repair Cycle", id="btn-repair")
            yield Button("Force Advance", id="btn-advance")

    async def on_mount(self) -> None:
        table = self.query_one("#goals-table", DataTable)
        table.add_columns("Goal", "Status", "Progress")
        self.app.activity_updates.subscribe(self._on_activity_update)
        await self.refresh_goals()

    def on_unmount(self) -> None:
        self.app.activity_updates.unsubscribe(self._on_activity_update)

    async def _on_activity_update(self, cache: dict) -> None:
        self._update_goals_table(cache.get("activities", []))

    def _update_goals_table(self, activities: list[dict]) -> None:
        table = self.query_one("#goals-table", DataTable)
        table.clear()
        log = self.query_one("#automation-log", Vertical)
        log.remove_children()
        if not activities:
            table.add_row("(no active goals)", "—", "—")
            return
        for act in activities:
            title = act.get("title", act.get("id", "Unknown"))
            status = act.get("status", "unknown")
            progress = f"{act.get('progress', 0)}%"
            table.add_row(title, status, progress)
            log.mount(Static(f"[dim]{act.get('id', '')[:8]} ... {status}[/dim]"))

    async def refresh_goals(self) -> None:
        try:
            activities = await self.app.jarvis_client.get_activities()
            self._update_goals_table(activities)
        except Exception as e:
            table = self.query_one("#goals-table", DataTable)
            table.clear()
            table.add_row("(error loading goals)", "—", "—")
            self.app.notify(f"Error loading goals: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            await self.refresh_goals()
        elif event.button.id == "btn-stop":
            try:
                activities = await self.app.jarvis_client.get_activities()
                cancelled = 0
                for act in activities:
                    aid = act.get("id")
                    if aid:
                        try:
                            await self.app.jarvis_client.cancel_activity(aid)
                            cancelled += 1
                        except Exception as e:
                            logger.warning("cancel_activity failed: %s", e)
                self.app.notify(f"Cancelled {cancelled} active goal(s)", severity="information")
                await self.refresh_goals()
            except Exception as e:
                self.app.notify(f"Error stopping goals: {e}", severity="error")
        elif event.button.id == "btn-repair":
            self.app.notify("Repair cycle runs automatically; use CLI: jarvis advanced repair", severity="information")
        elif event.button.id == "btn-advance":
            self.app.notify("Force advance runs automatically; no manual trigger needed", severity="information")
