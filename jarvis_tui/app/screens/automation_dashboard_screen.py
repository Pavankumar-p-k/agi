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
from textual.widgets import Label, Static, Button, ProgressBar
from jarvis_tui.app.screens.base_screen import JarvisScreen

class AutomationDashboardScreen(JarvisScreen):
    """
    TUI Automation Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# AUTOMATION DASHBOARD", id="screen-title")
        yield Label("Monitor active goals and autonomous workflows.")
        
        with Vertical(id="active-goal-container"):
            yield Label("## CURRENT GOAL")
            yield Static("[bold cyan]Transforming JARVIS UI into complete control surface[/bold cyan]")
            yield Label("Progress: 65%")
            yield ProgressBar(total=100, show_bar=True, id="goal-progress")
            
        yield Label("## EXECUTION LOG")
        yield Vertical(id="automation-log")
        
        with Horizontal(id="automation-actions"):
            yield Button("Stop All", id="btn-stop", variant="error")
            yield Button("Repair Cycle", id="btn-repair")
            yield Button("Force Advance", id="btn-advance")

    async def on_mount(self) -> None:
        self.query_one("#goal-progress", ProgressBar).progress = 65
