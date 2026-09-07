"""Session management."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

SESSION_DIR = Path.home() / ".jarvis" / "sessions"
LAST_SESSION_FILE = Path.home() / ".jarvis" / "last_session.txt"


class ConversationManager:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or "default"

    def add_message(self, role: str, content: str):
        pass

    def get_history(self) -> list[dict[str, Any]]:
        return []


def list_sessions() -> list[str]:
    return ["default"]


def get_last_session_id() -> str:
    return "default"


session_manager = ConversationManager()
