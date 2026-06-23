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

from rich.panel import Panel
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Footer, Label, ProgressBar, Static


class ReplayScreen(Screen):
    """
    Temporal replay mode for debugging agent reasoning.
    """
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Chat"),
        Binding("left", "step_back", "Step Back"),
        Binding("right", "step_forward", "Step Forward"),
        Binding("space", "toggle_play", "Play/Pause"),
    ]

    index = reactive(0)
    playing = reactive(False)

    # Mock history for now
    history = [
        {"agent": "NEXUS", "content": "Initializing research on 'quantum computing'...", "type": "thought"},
        {"agent": "SYSTEM", "content": "Searching academic databases...", "type": "tool_call"},
        {"agent": "NEXUS", "content": "Found 12 papers relevant to the query.", "type": "thought"},
        {"agent": "FORGE", "content": "Starting code generation for simulation...", "type": "thought"},
        {"agent": "SYSTEM", "content": "Writing file: quantum_sim.py", "type": "tool_call"},
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold blue]TEMPORAL REPLAY MODE[/bold blue]", id="replay-header")
        with Vertical(id="replay-container"):
            yield Static("", id="replay-viewer")
        with Horizontal(id="replay-controls"):
            yield Label("00:00", id="replay-time-start")
            yield ProgressBar(total=len(self.history)-1, show_bar=True, show_percentage=False, id="replay-progress")
            yield Label(f"{len(self.history):02}:00", id="replay-time-end")
        yield Footer()

    def watch_index(self, index: int) -> None:
        if hasattr(self, "history"):
            event = self.history[index]
            viewer = self.query_one("#replay-viewer", Static)
            progress = self.query_one("#replay-progress", ProgressBar)

            # Render event
            content = f"[bold magenta]{event['agent']}[/bold magenta]\n"
            content += f"[italic dim]{event['type']}[/italic dim]\n\n"
            content += event["content"]

            viewer.update(Panel(content, border_style="blue"))
            progress.progress = index

    def action_step_back(self) -> None:
        if self.index > 0:
            self.index -= 1

    def action_step_forward(self) -> None:
        if self.index < len(self.history) - 1:
            self.index += 1

    def action_toggle_play(self) -> None:
        self.playing = not self.playing
        if self.playing:
            self.set_interval(1.0, self.action_step_forward, id="play_timer")
        else:
            self.remove_timer("play_timer")
