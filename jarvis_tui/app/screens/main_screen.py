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

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from jarvis_tui.app.widgets.chat_stream import ChatStream
from jarvis_tui.app.widgets.cmd_palette import CommandPalette
from jarvis_tui.app.widgets.confirm_gate import ConfirmGate
from jarvis_tui.app.widgets.diff_pane import DiffPane
from jarvis_tui.app.widgets.hero_banner import HeroBanner
from jarvis_tui.app.widgets.input_bar import InputBar
from jarvis_tui.app.widgets.sidebar import Sidebar
from jarvis_tui.app.widgets.status_bar import StatusBar
from jarvis_tui.app.widgets.toast import ToastRack
from jarvis_tui.app.widgets.whisper_channel import WhisperChannel


class MainScreen(Screen):
    BINDINGS = [
        Binding("/", "show_palette('/')", "Show Commands"),
        Binding("@", "show_palette('@')", "Agent Roster"),
        Binding("!", "show_palette('!')", "Direct Tool"),
        Binding("#", "show_palette('#')", "Bookmarks"),
        Binding("ctrl+w", "toggle_whisper", "Agent Whisper Channel"),
        Binding("ctrl+d", "toggle_diff", "File Diff Pane"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Sidebar(id="sidebar")
            with Vertical(id="main-content"):
                yield HeroBanner(id="hero-banner")
                yield ChatStream(id="chat-stream")
                yield InputBar(id="input-bar")
            yield WhisperChannel(id="whisper-channel")
        yield DiffPane(
            old_content="def hello():\n    print('world')",
            new_content="def hello():\n    print('hello world')",
            filename="hello.py",
            id="diff-pane"
        )
        yield StatusBar(id="status-bar")
        yield CommandPalette(id="cmd-palette")
        yield ConfirmGate(id="confirm-gate")
        yield ToastRack(id="toast-rack")

    def action_show_palette(self, trigger: str = "/") -> None:
        palette = self.query_one("#cmd-palette", CommandPalette)
        palette.toggle(trigger)

    def action_toggle_whisper(self) -> None:
        whisper = self.query_one("#whisper-channel", WhisperChannel)
        whisper.toggle()

    def action_toggle_diff(self) -> None:
        diff = self.query_one("#diff-pane", DiffPane)
        diff.display = not diff.display

    def on_mount(self) -> None:
        self.title = "JARVIS"
        self.sub_title = "AI Operating System"
