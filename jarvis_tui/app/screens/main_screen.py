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
from jarvis_tui.app.widgets.navigation import Navigation
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
            old_content="# File diffs appear here when reviewing changes",
            new_content="# Use Ctrl+D to toggle this pane",
            filename="",
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

    def on_navigation_selected(self, message: Navigation.Selected) -> None:
        """Handle navigation selection from the sidebar."""
        self.app.handle_navigation(message.screen_name)

    def on_mount(self) -> None:
        self.title = "JARVIS"
        self.sub_title = "AI Operating System"
