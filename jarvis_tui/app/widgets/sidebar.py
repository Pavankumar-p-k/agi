from __future__ import annotations

import logging
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
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ProgressBar, Static

from jarvis_tui.app.widgets.navigation import Navigation
from jarvis_tui.app.widgets.todo_queue import TodoQueue
logger = logging.getLogger(__name__)


class Sidebar(Widget):
    """
    Sidebar with unified navigation, model selector, active agents, tool calls, and stats.
    """
    model_name = reactive("none")
    context_pct = reactive(0)
    cpu_usage = reactive(0)
    ram_usage = reactive(0)
    vram_usage = reactive(0)
    agents = reactive([]) # List of {"name": str, "status": str}

    def compose(self) -> ComposeResult:
        with Vertical(id="sidebar-container"):
            yield Label("NAVIGATION")
            yield Navigation(id="main-nav")

            yield Label("MODEL")
            yield Static(f" {self.model_name} ▾", id="model-selector", classes="selector")

            yield Label("ACTIVE AGENTS")
            yield Vertical(id="agent-list")

            yield Label("TOOL CALLS")
            yield Vertical(id="tool-calls")

            yield TodoQueue(id="todo-queue")

            yield Label("CONTEXT WINDOW")
            yield Static(f"{self.context_pct}% [0 / 128k]", id="ctx-label")
            yield ProgressBar(total=100, show_bar=True, show_percentage=False, id="ctx-progress")

            yield Label("SYSTEM")
            yield Static("CPU [dim]...[/dim]", id="cpu-stat")
            yield Static("RAM [dim]...[/dim]", id="ram-stat")
            yield Static("VRAM [dim]...[/dim]", id="vram-stat")

    def watch_agents(self, agents: list) -> None:
        try:
            container = self.query_one("#agent-list", Vertical)
            container.remove_children()
            for agent in agents:
                status = agent.get("status", "idle")
                color = "green" if status == "busy" else "yellow"
                container.mount(Static(f"● [bold {color}]{agent['name'].upper()}[/bold {color}] [dim]{status}[/dim]"))
        except Exception as e:
            logger.warning(f"sidebar watch_agents: {e}")

    def watch_model_name(self, name: str) -> None:
        try:
            self.query_one("#model-selector", Static).update(f" {name} ▾")
        except Exception as e:
            logger.warning(f"sidebar watch_model_name: {e}")

    def watch_context_pct(self, pct: int) -> None:
        try:
            self.query_one("#ctx-progress", ProgressBar).progress = pct
            self.query_one("#ctx-label", Static).update(f"{pct}% [{(pct*1280):.0f} / 128k]")
        except Exception as e:
            logger.warning(f"sidebar watch_context_pct: {e}")

    def watch_cpu_usage(self, val: int) -> None:
        self._update_stat("#cpu-stat", "CPU", val)

    def watch_ram_usage(self, val: int) -> None:
        self._update_stat("#ram-stat", "RAM", val)

    def watch_vram_usage(self, val: int) -> None:
        self._update_stat("#vram-stat", "VRAM", val)

    def _update_stat(self, selector: str, label: str, val: int) -> None:
        try:
            chars = "█" * (val // 10) + "░" * (10 - (val // 10))
            self.query_one(selector, Static).update(f"{label} {chars} [{val}%]")
        except Exception as e:
            logger.warning(f"sidebar _update_stat: {e}")

    def on_mount(self) -> None:
        # Wait for backend sync
        pass
