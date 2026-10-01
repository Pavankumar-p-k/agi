from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Footer, Label, ProgressBar, Static, TabbedContent, TabPane

from jarvis_tui.app.screens.base_screen import JarvisScreen


class ReplayScreen(JarvisScreen):
    """
    Read-only activity replay viewer.

    Fetches a ReplayDAG from the REST API and renders:
      - execution DAG (tree view)
      - chronological timeline (step-through)
      - decision trace
      - provider / tool / workflow metadata
      - duration / retries / failures
    """
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("left", "step_back", "Step Back"),
        Binding("right", "step_forward", "Step Forward"),
        Binding("space", "toggle_play", "Play/Pause"),
    ]

    index = reactive(0)
    playing = reactive(False)
    _play_timer = None

    def __init__(self, activity_id: str | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._activity_id = activity_id
        self._dag: dict | None = None
        self._activity_label: str = ""

    def compose(self) -> ComposeResult:
        yield Static("[bold blue]ACTIVITY REPLAY[/bold blue]", id="replay-header")
        with TabbedContent(id="replay-tabs"):
            with TabPane("Timeline", id="tab-timeline"):
                with Vertical(id="replay-container"):
                    yield Static("", id="replay-viewer")
                with Horizontal(id="replay-controls"):
                    yield Label("00:00", id="replay-time-start")
                    yield ProgressBar(total=100, show_bar=True, show_percentage=False, id="replay-progress")
                    yield Label("00:00", id="replay-time-end")
            with TabPane("DAG Tree", id="tab-dag"):
                yield ScrollableContainer(Static("", id="replay-dag-view"), id="replay-dag-container")
            with TabPane("Decisions", id="tab-decisions"):
                yield ScrollableContainer(Static("", id="replay-decisions-view"), id="replay-decisions-container")
            with TabPane("Summary", id="tab-summary"):
                yield ScrollableContainer(Static("", id="replay-summary-view"), id="replay-summary-container")
        yield Footer()

    async def on_mount(self) -> None:
        await self._load_replay()

    async def _load_replay(self) -> None:
        try:
            if self._activity_id:
                aid = self._activity_id
                label = aid[:16]
            else:
                activities = await self.app.jarvis_client.get_activities()
                if not activities:
                    self._show_empty("No recent activity")
                    return
                act = activities[0]
                aid = act.get("id") or act.get("node_id")
                label = act.get("title", act.get("id", "Unknown")[:16])
                if not aid:
                    self._show_empty("Activity has no ID")
                    return

            self._activity_label = label
            self._dag = await self.app.jarvis_client.get_activity_replay(aid)
            self._render_all()
        except Exception as e:
            viewer = self.query_one("#replay-viewer", Static)
            viewer.update(Panel(f"Failed to load replay: {e}", border_style="red"))

    def _show_empty(self, msg: str) -> None:
        for tab_id in ("replay-viewer", "replay-dag-view", "replay-decisions-view", "replay-summary-view"):
            try:
                self.query_one(f"#{tab_id}", Static).update(
                    Panel(msg, border_style="yellow")
                )
            except Exception:
                pass

    def _render_all(self) -> None:
        if not self._dag:
            return
        self._render_timeline()
        self._render_dag()
        self._render_decisions()
        self._render_summary()

    def _render_timeline(self) -> None:
        timeline = self._dag.get("timeline", [])
        if not timeline:
            viewer = self.query_one("#replay-viewer", Static)
            viewer.update(Panel("No timeline events.", border_style="yellow"))
            return
        progress = self.query_one("#replay-progress", ProgressBar)
        progress.total = max(len(timeline) - 1, 0)
        end_label = self.query_one("#replay-time-end", Label)
        end_label.update(f"{len(timeline):02}:00")
        self.index = 0

    def _render_dag(self) -> None:
        all_nodes = self._dag.get("all_nodes", {})
        root_id = self._dag.get("root_id")
        if not all_nodes or not root_id:
            viewer = self.query_one("#replay-dag-view", Static)
            viewer.update(Panel("No DAG data.", border_style="yellow"))
            return

        lines = []
        self._render_node_tree(root_id, all_nodes, lines, depth=0)
        viewer = self.query_one("#replay-dag-view", Static)
        viewer.update(Panel("\n".join(lines), title="Execution DAG", border_style="blue"))

    def _render_node_tree(self, node_id: str, all_nodes: dict, lines: list, depth: int) -> None:
        node = all_nodes.get(node_id)
        if not node:
            return
        indent = "  " * depth
        icon = self._node_icon(node.get("node_type", ""))
        status = node.get("status", "unknown")
        status_color = {"COMPLETED": "green", "FAILED": "red", "ERROR": "red",
                        "RUNNING": "cyan", "PENDING": "yellow", "SUSPENDED": "dim"}.get(status, "white")
        label = node.get("label", node_id)[:60]
        tool = node.get("tool")
        provider = node.get("provider")
        detail = ""
        if tool:
            detail = f" [dim]tool={tool}[/dim]"
        elif provider:
            detail = f" [dim]provider={provider}[/dim]"
        lines.append(
            f"{indent}{icon} [bold]{label[:50]}[/bold] [{status_color}]{status}[/{status_color}]{detail}"
        )
        for child_id in node.get("children", []):
            self._render_node_tree(child_id, all_nodes, lines, depth + 1)

    def _node_icon(self, node_type: str) -> str:
        return {"goal": "[blue]G[/blue]", "subgoal": "[cyan]S[/cyan]",
                "agent_call": "[magenta]A[/magenta]", "tool_call": "[yellow]T[/yellow]",
                "artifact": "[green]F[/green]", "milestone": "[white]M[/white]",
                "milestone": "[white]M[/white]"}.get(node_type, "[dim]?[/dim]")

    def _render_decisions(self) -> None:
        decisions = self._dag.get("decisions", [])
        if not decisions:
            viewer = self.query_one("#replay-decisions-view", Static)
            viewer.update(Panel("No decision trace data.", border_style="yellow"))
            return

        parts: list[str] = []
        for dec in decisions:
            parts.append(f"[bold]Decision:[/bold] {dec.get('decision_id', '?')[:12]}")
            parts.append(f"  Capability: {dec.get('capability', '?')}")
            parts.append(f"  Selected: {dec.get('selected_provider', '?')}")
            reasons = dec.get("reasons", [])
            if reasons:
                parts.append(f"  Scores: {', '.join(reasons)}")
            candidates = dec.get("candidates", [])
            if candidates:
                parts.append("  Candidate scores:")
                for c in candidates:
                    parts.append(
                        f"    {c.get('provider_id', '?')}: "
                        f"total={c.get('total_score', 0):.2f} "
                        f"priority={c.get('priority_score', 0):.2f} "
                        f"historical={c.get('historical_score', 0):.2f}"
                    )
            outcome = dec.get("outcome")
            if outcome:
                status = "SUCCESS" if outcome.get("success") else "FAILURE"
                parts.append(f"  Outcome: {status} (dur={outcome.get('duration_ms', 0):.0f}ms)")
            parts.append("")

        viewer = self.query_one("#replay-decisions-view", Static)
        viewer.update(Panel("\n".join(parts), title="Decision Trace", border_style="blue"))

    def _render_summary(self) -> None:
        dag = self._dag
        if not dag:
            return

        t = Table.grid(padding=(0, 1))
        t.add_column()
        t.add_column()

        t.add_row("[bold]Activity[/bold]", dag.get("activity_id", "?")[:20])
        t.add_row("[bold]Status[/bold]", self._dag_status(dag))
        t.add_row("[bold]Total Nodes[/bold]", str(dag.get("total_nodes", 0)))
        t.add_row("[bold]Failed Nodes[/bold]", str(dag.get("failed_nodes", 0)))
        t.add_row("[bold]Duration[/bold]", f"{dag.get('total_duration_seconds', 0):.1f}s")

        tools = dag.get("unique_tools", [])
        t.add_row("[bold]Tools[/bold]", ", ".join(tools[:8]) if tools else "none")

        providers = dag.get("unique_providers", [])
        t.add_row("[bold]Providers[/bold]", ", ".join(providers[:4]) if providers else "none")

        t.add_row("[bold]Total Retries[/bold]", str(dag.get("total_retries", 0)))
        t.add_row("[bold]Total Cost[/bold]", f"{dag.get('total_cost', 0):.4f}")

        viewer = self.query_one("#replay-summary-view", Static)
        viewer.update(Panel(t, title="Activity Summary", border_style="green"))

    def _dag_status(self, dag: dict) -> str:
        failed = dag.get("failed_nodes", 0)
        total = dag.get("total_nodes", 0)
        if failed > 0:
            return f"[red]{failed}/{total} FAILED[/red]"
        return "[green]ALL PASS[/green]"

    def _current_event(self) -> dict | None:
        timeline = self._dag.get("timeline", []) if self._dag else []
        if timeline and 0 <= self.index < len(timeline):
            return timeline[self.index]
        return None

    def _render_event(self) -> None:
        event = self._current_event()
        viewer = self.query_one("#replay-viewer", Static)
        if not event:
            viewer.update(Panel("No event at this position.", border_style="yellow"))
            return

        progress = self.query_one("#replay-progress", ProgressBar)
        start_label = self.query_one("#replay-time-start", Label)
        start_label.update(f"{self.index:02}:00")

        ts = event.get("timestamp", 0)
        label = event.get("label", "?")
        node_type = event.get("node_type", "?")
        status = event.get("status", "?")
        duration = event.get("duration_seconds")
        detail = event.get("detail", "")

        lines = [
            f"[bold magenta]Step {self.index + 1}[/bold magenta]",
            f"[italic dim]{node_type}[/italic dim]",
            f"",
            f"[bold]Node:[/bold] {event.get('node_id', '?')[:24]}",
            f"[bold]Label:[/bold] {label}",
            f"[bold]Status:[/bold] {status}",
        ]
        if duration is not None:
            lines.append(f"[bold]Duration:[/bold] {duration:.1f}s")
        if detail:
            lines.append(f"[bold]Detail:[/bold] {detail}")
        if ts:
            lines.append(f"[bold]Timestamp:[/bold] {ts:.1f}")

        rendered = "\n".join(lines)
        viewer.update(Panel(rendered, border_style="blue"))
        progress.progress = self.index

    def watch_index(self, index: int) -> None:
        if self._dag:
            self._render_event()

    def action_step_back(self) -> None:
        if self.index > 0:
            self.index -= 1

    def action_step_forward(self) -> None:
        timeline = self._dag.get("timeline", []) if self._dag else []
        if self.index < len(timeline) - 1:
            self.index += 1

    def action_toggle_play(self) -> None:
        timeline = self._dag.get("timeline", []) if self._dag else []
        if not timeline:
            return
        self.playing = not self.playing
        if self.playing:
            self._play_timer = self.set_interval(1.0, self.action_step_forward)
        else:
            if self._play_timer is not None:
                self._play_timer.stop()
                self._play_timer = None
