from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.console import RenderableType
from rich.align import Align

from rich.box import SQUARE

import re

class MessageWidget(Static):
    """
    Individual message widget with Sparkline support.
    """
    expanded = reactive(True)

    def __init__(self, sender: str, content: str, msg_type: str = "agent", **kwargs):
        super().__init__(**kwargs)
        self.sender = sender
        self.content = content
        self.msg_type = msg_type
        if len(content.splitlines()) > 5 and msg_type in ("tool_result", "agent"):
            self.expanded = False

    def _render_sparkline(self, data: list[float]) -> Text:
        chars = " ▂▃▄▅▆▇█"
        if not data: return Text("")
        m = max(data)
        if m == 0: m = 1
        spark = "".join(chars[int(v / m * 7)] for v in data)
        return Text(spark, style="green bold")

    def render(self) -> RenderableType:
        # Auto-detect number heavy analysis for sparklines
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", self.content)
        if len(numbers) > 5 and self.msg_type == "agent":
            try:
                data = [float(n) for n in numbers[:20]]
                spark = self._render_sparkline(data)
                self.content = self.content + "\n\n" + spark.markup
            except: pass

        display_text = Text.from_markup(self.content)
        if not self.expanded:
            lines = self.content.splitlines()
            display_text = Text.from_markup(f"{lines[0]}\n[dim italic]... (+{len(lines)-1} lines) [Space to expand][/dim italic]")

        if self.msg_type == "user":
            return Panel(display_text, title="YOU", title_align="right", border_style="blue")
        elif self.msg_type == "tool_call":
            return Panel(Text.assemble(("▶ tool: ", "cyan"), (self.content, "cyan")), border_style="cyan", box=SQUARE)
        elif self.msg_type == "thinking":
            return Panel(display_text, title="THINKING", border_style="yellow", box=SQUARE)
        elif self.msg_type == "system":
            return Align.center(Text(f"--- {self.content} ---", style="dim"))
        else:
            return Panel(display_text, title=self.sender.upper(), title_align="left", border_style="green")

    def on_click(self) -> None:
        self.expanded = not self.expanded

    def on_key(self, event: events.Key) -> None:
        if event.key == "space":
            self.expanded = not self.expanded
            event.stop()

class ChatStream(Widget):
    """
    The main conversation stream.
    """
    messages = reactive([])

    def compose(self) -> ComposeResult:
        yield MessageWidget("SYSTEM", "Synchronizing with JARVIS AI OS...", msg_type="system")

    def add_message(self, sender: str, content: str, msg_type: str = "agent") -> None:
        new_msg = MessageWidget(sender, content, msg_type)
        self.mount(new_msg)
        self.scroll_end()
