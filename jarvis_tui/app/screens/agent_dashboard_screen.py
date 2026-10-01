from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Static, Button, DataTable, Input
from jarvis_tui.app.screens.base_screen import JarvisScreen


class AgentDashboardScreen(JarvisScreen):
    """
    TUI Agent Dashboard UI.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agents: list[dict] = []
        self._running: list[dict] = []

    def compose_main(self) -> ComposeResult:
        yield Label("# AGENT DASHBOARD", id="screen-title")
        yield Label("Monitor and deploy autonomous agents.")

        yield DataTable(id="agents-table")

        with Vertical(id="task-input-area"):
            yield Label("## RUN TASK")
            yield Label("", id="task-agent-label")
            yield Input(placeholder="Enter task description...", id="task-input")
            with Horizontal(id="task-buttons"):
                yield Button("Submit", id="btn-submit-task", variant="primary")
                yield Button("Cancel", id="btn-cancel-task")

        yield Label("## RUNNING TASKS")
        yield Static("", id="running-progress")

        with Horizontal(id="agent-actions"):
            yield Button("Refresh", id="btn-refresh", variant="primary")
            yield Button("Run Task", id="btn-run")

    def on_mount(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.add_columns("Name", "Modes", "Description")
        table.cursor_type = "row"
        self.query_one("#task-input-area").display = False
        self.app.activity_updates.subscribe(self._on_activity_update)
        self.run_worker(self._refresh_agents())

    def on_unmount(self) -> None:
        self.app.activity_updates.unsubscribe(self._on_activity_update)

    async def _on_activity_update(self, cache: dict) -> None:
        activities = cache.get("activities", [])
        running = [a for a in activities if a.get("status", "").upper() in ("RUNNING", "PENDING")]
        self._running = running
        progress = self.query_one("#running-progress", Static)
        if not running:
            progress.update("[dim]No running tasks[/dim]")
        else:
            lines = []
            for a in running:
                title = a.get("title", a.get("id", "?"))[:40]
                status = a.get("status", "?")
                progress_pct = a.get("progress", a.get("progress_pct", ""))
                lines.append(f"  [bold]{title}[/bold]  [{status}]  {progress_pct}")
            progress.update("\n".join(lines))

    async def _refresh_agents(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        table.clear()
        try:
            data = await self.app.jarvis_client.get_agents()
            self._agents = data.get("agents", [])
            for a in self._agents:
                table.add_row(
                    a.get("name", "N/A"),
                    ", ".join(a.get("modes", [])),
                    a.get("description", "")
                )
        except Exception as e:
            self.app.notify(f"Error fetching agents: {e}", severity="error")

    def show_task_input(self) -> None:
        table = self.query_one("#agents-table", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self._agents):
            self.app.notify("Select an agent first", severity="warning")
            return
        agent = self._agents[table.cursor_row]
        name = agent.get("name", "N/A")
        self.query_one("#task-agent-label", Label).update(f"Agent: [bold]{name}[/bold]")
        self.query_one("#task-input", Input).value = ""
        self.query_one("#task-input", Input).focus()
        self.query_one("#task-input-area").display = True

    def hide_task_input(self) -> None:
        self.query_one("#task-input-area").display = False

    async def run_agent_task(self, name: str, task: str) -> None:
        self.hide_task_input()
        try:
            result = await self.app.jarvis_client.run_agent(name, task)
            activity_id = result.get("activity_id", result.get("id"))
            if activity_id:
                self.app.notify(f"Agent '{name}' started (ID: {activity_id[:12]}...)", severity="information")
            else:
                self.app.notify(f"Agent '{name}' started", severity="information")
        except Exception as e:
            self.app.notify(f"Failed to run agent: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            await self._refresh_agents()
        elif event.button.id == "btn-run":
            self.show_task_input()
        elif event.button.id == "btn-submit-task":
            table = self.query_one("#agents-table", DataTable)
            if table.cursor_row is not None and table.cursor_row < len(self._agents):
                name = self._agents[table.cursor_row].get("name", "")
                task_input = self.query_one("#task-input", Input)
                task = task_input.value.strip()
                if not task:
                    self.app.notify("Please enter a task description", severity="warning")
                    task_input.focus()
                    return
                await self.run_agent_task(name, task)
        elif event.button.id == "btn-cancel-task":
            self.hide_task_input()
