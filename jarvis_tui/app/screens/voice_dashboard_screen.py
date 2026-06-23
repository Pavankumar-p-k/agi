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

class VoiceDashboardScreen(JarvisScreen):
    """
    TUI Voice Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# VOICE CONTROL", id="screen-title")
        yield Label("Manage offline STT, TTS and wake word detection.")
        
        with Vertical(id="voice-status-container"):
            yield Label("## ENGINE STATUS")
            yield Static("Wake Word: [bold green]LISTENING (JARVIS)[/bold green]")
            yield Static("STT Engine: [bold green]READY (Whisper/Local)[/bold green]")
            yield Static("TTS Engine: [bold green]READY (Chatterbox)[/bold green]")
            
        yield Label("## RECENT TRANSCRIPTS")
        yield Vertical(id="transcript-list")
        
        with Horizontal(id="voice-actions"):
            yield Button("Push to Talk", id="btn-ptt", variant="primary")
            yield Button("Toggle Wake Word", id="btn-wake")
            yield Button("Test TTS", id="btn-tts")
