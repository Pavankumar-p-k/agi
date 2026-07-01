from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Static, Button
from jarvis_tui.app.screens.base_screen import JarvisScreen

class VoiceDashboardScreen(JarvisScreen):
    """
    TUI Voice Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# VOICE CONTROL", id="screen-title")
        yield Label("Manage offline STT, TTS and wake word detection.")
        
        with Vertical(id="voice-status-container"):
            yield Label("## ENGINE STATUS")
            yield Static("Loading voice status...", id="voice-wake")
            yield Static("", id="voice-stt")
            yield Static("", id="voice-tts")
            
        yield Label("## RECENT TRANSCRIPTS")
        yield Vertical(id="transcript-list")
        
        with Horizontal(id="voice-actions"):
            yield Button("Push to Talk", id="btn-ptt", variant="primary")
            yield Button("Toggle Wake Word", id="btn-wake")
            yield Button("Test TTS", id="btn-tts")

    async def on_mount(self) -> None:
        await self.refresh_voice_status()

    async def refresh_voice_status(self) -> None:
        try:
            data = await self.app.jarvis_client.get_diagnostics()
            voice = data.get("data", {}).get("voice", {})
            
            wake = voice.get("wake_word_available", False)
            stt = voice.get("stt_available", False)
            tts = voice.get("tts_available", False)
            enabled = voice.get("enabled", False)
            
            def status_tag(available: bool) -> str:
                return "[bold green]READY[/bold green]" if available else "[bold red]UNAVAILABLE[/bold red]"
            
            self.query_one("#voice-wake", Static).update(
                f"Wake Word: {'[bold green]LISTENING (JARVIS)[/bold green]' if wake else '[bold red]NOT AVAILABLE[/bold red]'}"
            )
            self.query_one("#voice-stt", Static).update(
                f"STT Engine: {status_tag(stt)}" + (" (Whisper/Local)" if stt else "")
            )
            self.query_one("#voice-tts", Static).update(
                f"TTS Engine: {status_tag(tts)}" + (" (Chatterbox)" if tts else "")
            )
        except Exception as e:
            self.query_one("#voice-wake", Static).update("Wake Word: [bold red]OFFLINE[/bold red]")
            self.query_one("#voice-stt", Static).update(f"STT Engine: [bold red]OFFLINE ({e})[/bold red]")
            self.query_one("#voice-tts", Static).update("TTS Engine: [bold red]OFFLINE[/bold red]")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ptt":
            self.app.notify("Push to Talk not available in TUI; use the Web UI or desktop app", severity="information")
        elif event.button.id == "btn-wake":
            self.app.notify("Wake word toggle not available in TUI; use CLI: jarvis advanced voice toggle-wake", severity="information")
        elif event.button.id == "btn-tts":
            self.app.notify("Test TTS not available in TUI; use CLI: jarvis advanced voice test-tts", severity="information")
