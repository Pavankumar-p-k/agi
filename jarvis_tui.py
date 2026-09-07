"""jarvis TUI - Terminal User Interface for JARVIS."""
from __future__ import annotations

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Log, Static, TabbedContent, TabPane
from textual.screen import Screen
from textual.message import Message
from rich.text import Text

from core.agent_loop import stream_agent_loop
from core.configuration import configuration
from core.build.service import build_service
from core.pipeline import process_message
from core.pipeline.messages import Request


class ChatMessage(Message):
    """Message for chat output."""
    def __init__(self, text: str, is_user: bool = False) -> None:
        self.text = text
        self.is_user = is_user
        super().__init__()


class ChatInput(Input):
    """Chat input with send binding."""
    
    BINDINGS = [
        Binding("enter", "send", "Send", show=True),
    ]
    
    def action_send(self) -> None:
        if self.value.strip():
            self.post_message(ChatMessage(self.value.strip(), is_user=True))
            self.value = ""


class ChatLog(Log):
    """Chat message log."""
    
    def on_mount(self) -> None:
        self.write("[dim]JARVIS TUI Chat[/dim]\nType a message and press Enter to send.\n")


class BuildPanel(Static):
    """Build management panel."""
    
    def on_mount(self) -> None:
        self.update_builds()
    
    def update_builds(self) -> None:
        projects = build_service.list_all()
        if not projects:
            self.update("[dim]No builds[/dim]")
            return
        
        lines = []
        for p in projects:
            status_color = "green" if p["status"] == "done" else "yellow" if p["status"] == "running" else "red"
            lines.append(f"[{status_color}]{p['status']}[/{status_color}] {p['name']} - {p['goal'][:40]}")
        self.update("\n".join(lines))


class SystemStatus(Static):
    """System status panel."""
    
    def on_mount(self) -> None:
        self.update_status()
    
    def update_status(self) -> None:
        from core.pipeline import get_pipeline
        pipeline = get_pipeline()
        
        lines = [
            f"Pipeline: {len(pipeline.stages)} stages",
            f"Chat model: {configuration.get('llm.chat_model', 'N/A')}",
            f"Dev mode: {configuration.get('server.dev_mode', False)}",
        ]
        self.update("\n".join(lines))


class JarvisTUI(App):
    """JARVIS Terminal User Interface."""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
        grid-rows: 1fr 3fr;
        grid-columns: 2fr 1fr;
    }
    
    #chat-container {
        column-span: 2;
        border: solid cyan;
    }
    
    #build-panel {
        border: solid green;
        padding: 1;
    }
    
    #status-panel {
        border: solid yellow;
        padding: 1;
    }
    
    ChatLog {
        height: 100%;
        border: solid cyan;
    }
    
    ChatInput {
        dock: bottom;
        border: solid cyan;
    }
    
    .panel-title {
        text-style: bold;
        color: cyan;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "clear_chat", "Clear"),
        Binding("ctrl+b", "focus_builds", "Builds"),
        Binding("ctrl+s", "focus_status", "Status"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Footer()
        
        with Container(id="chat-container"):
            yield ChatLog(id="chat-log")
            yield ChatInput(placeholder="Type a message...", id="chat-input")
        
        yield BuildPanel(id="build-panel")
        yield SystemStatus(id="status-panel")
    
    def on_mount(self) -> None:
        self.title = "JARVIS TUI"
        self.sub_title = "AI Life Operating System"
        # Focus chat input
        self.query_one("#chat-input", ChatInput).focus()
    
    def on_chat_message(self, message: ChatMessage) -> None:
        """Handle incoming chat messages."""
        chat_log = self.query_one("#chat-log", ChatLog)
        
        if message.is_user:
            chat_log.write(f"[bold cyan]You:[/bold cyan] {message.text}")
            self.run_worker(self._process_message(message.text), exclusive=True)
        else:
            chat_log.write(f"[bold green]JARVIS:[/bold green] {message.text}")
    
    async def _process_message(self, text: str) -> None:
        """Process message through pipeline."""
        chat_log = self.query_one("#chat-log", ChatLog)
        
        try:
            req = Request(text=text, transport="tui", user_id="tui_user")
            response = await process_message(req)
            
            if response.error:
                chat_log.write(f"[bold red]Error:[/bold red] {response.error}")
            else:
                chat_log.write(f"[bold green]JARVIS:[/bold green] {response.text}")
                
        except Exception as e:
            chat_log.write(f"[bold red]Error:[/bold red] {e}")
    
    def action_clear_chat(self) -> None:
        """Clear chat log."""
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.clear()
    
    def action_focus_builds(self) -> None:
        """Focus build panel."""
        self.query_one("#build-panel", BuildPanel).focus()
    
    def action_focus_status(self) -> None:
        """Focus status panel."""
        self.query_one("#status-panel", SystemStatus).focus()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "chat-input" and event.value.strip():
            self.post_message(ChatMessage(event.value.strip(), is_user=True))
            event.input.value = ""


if __name__ == "__main__":
    app = JarvisTUI()
    app.run()