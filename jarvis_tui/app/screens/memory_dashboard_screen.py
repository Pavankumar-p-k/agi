from __future__ import annotations

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
        await self.refresh_memories()

    async def refresh_memories(self) -> None:
        table = self.query_one("#memory-table", DataTable)
        table.clear()
        try:
            stats = await self.app.jarvis_client.get_memory_stats()
            memories = stats.get("memories", stats.get("stats", stats.get("data", [])))
            if not memories:
                table.add_row("(no data)", "—", "Memory stats unavailable from backend")
                return
            if isinstance(memories, dict):
                for k, v in memories.items():
                    label = k.upper().replace("_", " ")
                    if isinstance(v, dict):
                        table.add_row(label, str(v.get("count", v.get("entries", "—"))), v.get("description", str(v)))
                    else:
                        table.add_row(label, str(v), "")
            elif isinstance(memories, list):
                for m in memories:
                    label = m.get("type", m.get("name", "Unknown")).upper()
                    count = str(m.get("count", m.get("entries", m.get("value", "—"))))
                    desc = m.get("description", m.get("summary", ""))
                    table.add_row(label, count, desc)
        except Exception as e:
            table.add_row("(error)", "—", f"Could not load memory stats: {e}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            await self.refresh_memories()
        elif event.button.id == "btn-prune":
            self.app.notify("Prune from CLI: jarvis advanced memory prune", severity="information")
