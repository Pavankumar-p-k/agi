from __future__ import annotations

from ..bootstrap import build_jarvis_os


class VoiceInterface:
    def __init__(self) -> None:
        self.runtime = build_jarvis_os()

    def handle_transcript(self, transcript: str) -> dict:
        return self.runtime.handle_prompt(transcript)
