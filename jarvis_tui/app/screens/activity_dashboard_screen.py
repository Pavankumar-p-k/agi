from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Static, Header, Footer, Label, Tree, RichLog
from textual import work

from jarvis_tui.app.screens.base_screen import JarvisScreen

logger = logging.getLogger(__name__)


class ActivityDashboardScreen(JarvisScreen):
    """Browse and manage the activity graph."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("t", "show_tree", "Tree View"),
        Binding("d", "show_detail", "Detail"),
        Binding("p", "pause_activity", "Pause"),
        Binding("s", "resume_activity", "Resume"),
        Binding("c", "cancel_activity", "Cancel"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._activities: list[dict] = []
        self._selected_id: str | None = None

    def compose_main(self) -> ComposeResult:
        yield Label("# ACTIVITY GRAPH", id="screen-title")
        yield Static("Browse, inspect, and manage activity graph nodes.", id="screen-subtitle")
        with Horizontal(id="activity-layout"):
            with Vertical(id="activity-list-panel"):
                yield Label("Activities", classes="panel-title")
                yield DataTable(id="activities-table", classes="activity-table")
                with Horizontal(id="activity-list-actions"):
                    yield Button("Refresh", id="btn-refresh", variant="primary")
                    yield Button("Tree", id="btn-tree", variant="default")
                    yield Button("Detail", id="btn-detail", variant="default")
            with Vertical(id="activity-detail-panel"):
                yield Label("Details", classes="panel-title")
                yield RichLog(id="activity-detail", highlight=True, markup=True)
                yield RichLog(id="activity-timeline", highlight=True, markup=True)
        with Horizontal(id="activity-actions"):
            yield Button("Pause", id="btn-pause", variant="warning")
            yield Button("Resume", id="btn-resume", variant="primary")
            yield Button("Cancel", id="btn-cancel", variant="error")

    async def on_mount(self) -> None:
        table = self.query_one("#activities-table", DataTable)
        table.add_columns("ID", "Goal", "Status", "Type", "Depth", "Agent")
        table.cursor_type = "row"
        await self.refresh_activities()

    async def refresh_activities(self) -> None:
        table = self.query_one("#activities-table", DataTable)
        detail = self.query_one("#activity-detail", RichLog)
        detail.clear()
        table.clear()
        try:
            self._activities = await self.app.jarvis_client.get_activities()
            for a in self._activities:
                agent = a.get("agent_id") or ""
                table.add_row(
                    a.get("node_id", "")[:12],
                    a.get("label", "")[:50],
                    a.get("status", ""),
                    a.get("node_type", ""),
                    str(a.get("depth", 0)),
                    agent[:12],
                )
            self.app.notify(f"Loaded {len(self._activities)} activities", severity="information")
        except Exception as e:
            self.app.notify(f"Error fetching activities: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-refresh":
            self.action_refresh()
        elif button_id == "btn-tree":
            self.action_show_tree()
        elif button_id == "btn-detail":
            self.action_show_detail()
        elif button_id == "btn-pause":
            self.action_pause_activity()
        elif button_id == "btn-resume":
            self.action_resume_activity()
        elif button_id == "btn-cancel":
            self.action_cancel_activity()

    def _get_selected_id(self) -> str | None:
        table = self.query_one("#activities-table", DataTable)
        row = table.cursor_row
        if row is None:
            self.app.notify("No activity selected", severity="warning")
            return None
        try:
            return table.get_row_at(row)[0]
        except Exception as e:
            logger.warning("_get_selected_id get_row_at failed: %s", e)
            return None

    def action_refresh(self) -> None:
        self.set_focus(None)
        self.run_worker(self.refresh_activities())

    def action_show_tree(self) -> None:
        aid = self._get_selected_id()
        if not aid:
            return
        self._selected_id = aid
        self._load_tree(aid)

    @work(thread=False)
    async def _load_tree(self, aid: str) -> None:
        detail = self.query_one("#activity-detail", RichLog)
        detail.clear()
        detail.write("[bold yellow]Loading tree...[/]")
        try:
            data = await self.app.jarvis_client.get_activity_tree(aid)
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])
            detail.clear()
            detail.write(f"[bold cyan]Activity Tree: {aid[:16]}[/]")
            detail.write(f"  Nodes: {len(nodes)}  Edges: {len(edges)}")
            detail.write("")
            children: dict[str, list] = {}
            for n in nodes:
                p = n.get("parent_id") or ""
                children.setdefault(p, []).append(n)
            def _print_tree(parent_id: str, indent: int = 0):
                for n in children.get(parent_id, []):
                    icon = {"PENDING": "○", "RUNNING": "▶", "COMPLETED": "✓", "FAILED": "✗", "SUSPENDED": "⏸", "CANCELLED": "⊘"}.get(n.get("status", ""), "?")
                    agent = f" [dim]{n.get('agent_id', '')}[/]" if n.get("agent_id") else ""
                    detail.write(f"{'  ' * indent}{icon} [bold]{n.get('node_type', '')}[/]:{n.get('label', '')[:60]}{agent} [{n.get('status', '')}]")
                    _print_tree(n.get("node_id", ""), indent + 1)
            _print_tree("")
            if edges:
                detail.write("")
                detail.write("[bold]Edges:[/]")
                for e in edges[:20]:
                    detail.write(f"  {e.get('from_node_id','')[:12]} → {e.get('to_node_id','')[:12]} [{e.get('edge_type','')}]")
                if len(edges) > 20:
                    detail.write(f"  ... and {len(edges) - 20} more")
        except Exception as e:
            detail.write(f"[red]Error: {e}[/]")

    def action_show_detail(self) -> None:
        aid = self._get_selected_id()
        if not aid:
            return
        self._selected_id = aid
        self._load_detail(aid)

    @work(thread=False)
    async def _load_detail(self, aid: str) -> None:
        detail = self.query_one("#activity-detail", RichLog)
        detail.clear()
        detail.write("[bold yellow]Loading...[/]")
        try:
            client = self.app.jarvis_client
            node = await client.get_activity_detail(aid)
            summary = await client.get_activity_summary(aid)
            detail.clear()
            detail.write(f"[bold cyan]Activity: {node.get('label', '')}[/]")
            detail.write(f"  [bold]ID:[/] {node.get('node_id', '')}")
            detail.write(f"  [bold]Type:[/] {node.get('node_type', '')}")
            detail.write(f"  [bold]Status:[/] {node.get('status', '')}")
            detail.write(f"  [bold]Depth:[/] {node.get('depth', 0)}")
            if node.get("agent_id"):
                detail.write(f"  [bold]Agent:[/] {node['agent_id']}")
            if node.get("workflow_id"):
                detail.write(f"  [bold]Workflow:[/] {node['workflow_id']}")
            if node.get("parent_id"):
                detail.write(f"  [bold]Parent:[/] {node['parent_id']}")
            detail.write("")
            detail.write("[bold]Summary:[/]")
            detail.write(f"  Total nodes: {summary.get('total_nodes', 0)}")
            detail.write(f"  Max depth: {summary.get('depth', 0)}")
            detail.write(f"  Agents: {', '.join(summary.get('agents_used', [])) or 'none'}")
            by_status = summary.get("by_status", {})
            if by_status:
                detail.write("  By status:")
                for s, c in sorted(by_status.items()):
                    detail.write(f"    {s}: {c}")
        except Exception as e:
            detail.write(f"[red]Error: {e}[/]")

    def action_pause_activity(self) -> None:
        aid = self._get_selected_id()
        if not aid:
            return
        self._selected_id = aid
        self._do_pause(aid)

    @work(thread=False)
    async def _do_pause(self, aid: str) -> None:
        try:
            r = await self.app.jarvis_client.pause_activity(aid)
            self.app.notify(f"Paused: {r.get('status', 'ok')}", severity="warning")
            await self.refresh_activities()
        except Exception as e:
            self.app.notify(f"Error pausing: {e}", severity="error")

    def action_resume_activity(self) -> None:
        aid = self._get_selected_id()
        if not aid:
            return
        self._selected_id = aid
        self._do_resume(aid)

    @work(thread=False)
    async def _do_resume(self, aid: str) -> None:
        try:
            r = await self.app.jarvis_client.resume_activity(aid)
            self.app.notify(f"Resumed: {r.get('status', 'ok')}", severity="information")
            await self.refresh_activities()
        except Exception as e:
            self.app.notify(f"Error resuming: {e}", severity="error")

    def action_cancel_activity(self) -> None:
        aid = self._get_selected_id()
        if not aid:
            return
        self._selected_id = aid
        self._do_cancel(aid)

    @work(thread=False)
    async def _do_cancel(self, aid: str) -> None:
        try:
            r = await self.app.jarvis_client.cancel_activity(aid)
            self.app.notify(f"Cancelled: {r.get('status', 'ok')}", severity="error")
            await self.refresh_activities()
        except Exception as e:
            self.app.notify(f"Error cancelling: {e}", severity="error")
