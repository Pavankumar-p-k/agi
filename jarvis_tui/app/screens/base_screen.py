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
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from jarvis_tui.app.widgets.sidebar import Sidebar
from jarvis_tui.app.widgets.status_bar import StatusBar
from jarvis_tui.app.widgets.toast import ToastRack
from jarvis_tui.app.widgets.navigation import Navigation


class JarvisScreen(Screen):
    """
    Base screen for all JARVIS TUI screens.
    Includes persistent sidebar and status bar.
    """
    BINDINGS = [
        Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Sidebar(id="sidebar")
            with Vertical(id="main-content"):
                yield from self.compose_main()
        yield StatusBar(id="status-bar")
        yield ToastRack(id="toast-rack")

    def compose_main(self) -> ComposeResult:
        """Override this to add main content."""
        yield Vertical()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def on_navigation_selected(self, message: Navigation.Selected) -> None:
        """Handle navigation selection."""
        self.app.handle_navigation(message.screen_name)
