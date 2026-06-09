from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label


class InputBar(Widget):
    """
    Vim-style modal input with ghost text and code detection.
    """
    mode = reactive("INSERT")
    ghost_text = reactive("")
    is_code = reactive(False)

    BINDINGS = [
        Binding("escape", "switch_mode", "Switch Mode"),
        Binding("tab", "accept_ghost", "Accept completion"),
    ]

    def compose(self) -> ComposeResult:
        yield Label(f" {self.mode} ", id="mode-badge")
        yield Label("", id="code-badge")
        # Use a container to keep input and ghost text together
        with Horizontal(id="input-container"):
            yield Input(placeholder="Ask JARVIS anything...", id="chat-input")
            yield Label("", id="ghost-label")

    def watch_mode(self, mode: str) -> None:
        try:
            badge = self.query_one("#mode-badge", Label)
            badge.update(f" {mode} ")
            if mode == "INSERT":
                badge.styles.background = "#1b4614"
                badge.styles.color = "#7ab948"
            else:
                badge.styles.background = "#3e3e3c"
                badge.styles.color = "#c2c0b6"
        except Exception:
            pass

    def watch_is_code(self, is_code: bool) -> None:
        badge = self.query_one("#code-badge", Label)
        badge.update(" [code block] " if is_code else "")
        badge.styles.display = "block" if is_code else "none"

        inp = self.query_one("#chat-input", Input)
        if is_code:
            inp.styles.text_style = "bold italic" # Mono-like hint
        else:
            inp.styles.text_style = "none"

    def action_switch_mode(self) -> None:
        self.mode = "NORMAL" if self.mode == "INSERT" else "INSERT"
        inp = self.query_one("#chat-input", Input)
        if self.mode == "INSERT":
            inp.focus()
        else:
            self.app.focus_next()

    SUGGESTIONS = [
        "/research", "/codegen", "/model", "/theme", "/agent", "/vault",
        "/export", "/clear", "/exit", "/replay", "/confirm", "/diff", "/session",
        "@nexus", "@forge", "@scout", "@oracle",
        "!web_search", "!read_file", "!write_file", "!ls",
        "summarize the last tool results", "explain this code", "fix the bug"
    ]

    def on_input_changed(self, event: Input.Changed) -> None:
        # Code detection logic
        lines = event.value.splitlines()
        self.is_code = len(lines) > 1 or any(kw in event.value for kw in ["def ", "class ", "{", "import "])

        # Dynamic ghost-text logic
        val = event.value.lower()
        self.ghost_text = ""

        if val.strip():
            # Find all matching suggestions, pick the best (shortest matching)
            matches = [s for s in self.SUGGESTIONS if s.lower().startswith(val)]
            if matches:
                # Sort by length to pick the most concise match first
                matches.sort(key=len)
                best_match = matches[0]
                self.ghost_text = best_match[len(val):]

        try:
            label = self.query_one("#ghost-label", Label)
            label.update(self.ghost_text)
        except Exception: pass

    def _on_key(self, event: events.Key) -> None:
        """Handle global triggers even when input is focused."""
        if event.key == "/" and not self.query_one("#chat-input", Input).value:
            self.screen.action_show_palette("/")
            event.stop()
            event.prevent_default()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            msg = event.value
            if self.is_code:
                msg = f"```python\n{msg}\n```"

            try:
                chat = self.screen.query_one("#chat-stream")
                chat.add_message("YOU", msg, msg_type="user")
                self.run_worker(self.send_to_backend(msg))
            except Exception:
                pass

            inp = self.query_one("#chat-input", Input)
            inp.value = ""
            self.is_code = False

    async def send_to_backend(self, message: str) -> None:
        try:
            await self.app.jarvis_client.execute_prompt(message)
        except Exception as e:
            try:
                chat = self.screen.query_one("#chat-stream")
                chat.add_message("SYSTEM", f"Error: {str(e)}", msg_type="agent")
            except Exception:
                pass

    def action_accept_ghost(self) -> None:
        if self.ghost_text:
            inp = self.query_one("#chat-input", Input)
            inp.value += self.ghost_text
            self.ghost_text = ""
            self.query_one("#ghost-label", Label).update("")
