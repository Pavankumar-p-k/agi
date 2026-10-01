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

from __future__ import annotations

import json
import logging
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

logger = logging.getLogger(__name__)


class WhisperChannel(Widget):
    """
    Internal monologue/agent-to-agent channel (Ctrl+W toggle).
    Shows real agent events from the backend activity stream.
    """
    def __init__(self, jarvis_client: Any | None = None, **kwargs):
        super().__init__(**kwargs)
        self._client = jarvis_client
        self._messages: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold magenta]AGENT WHISPER CHANNEL[/bold magenta]")
            yield Static("Waiting for agent activity...", id="whisper-status", classes="whisper")

    def on_mount(self) -> None:
        self.display = False
        self.styles.width = 40
        self.styles.dock = "right"
        self.styles.background = "#2a1a2a"
        self.styles.border_left = ("solid", "#4a2a4a")
        self.styles.padding = 1
        self._load_recent_activity()

    def _load_recent_activity(self) -> None:
        if not self._client:
            return
        try:
            activities = self._client.get_activities(limit=10)
            if isinstance(activities, dict):
                items = activities.get("items", activities.get("activities", []))
            elif isinstance(activities, list):
                items = activities
            else:
                items = []
            for act in items:
                agent = act.get("agent_name", act.get("name", "AGENT"))
                status = act.get("status", act.get("state", "idle"))
                goal = act.get("goal", act.get("description", ""))
                msg = f"{agent} -> {status.upper()}: '{goal}'"
                self._messages.append(msg)
                self.mount(Static(msg, classes="whisper"))
            status = self.query_one("#whisper-status", Static)
            if self._messages:
                status.display = False
        except Exception as e:
            logger.warning("WhisperChannel load: %s", e)

    def add_message(self, sender: str, target: str, message: str) -> None:
        msg = f"{sender} -> {target}: '{message}'"
        self._messages.append(msg)
        try:
            self.mount(Static(msg, classes="whisper"))
            status = self.query_one("#whisper-status", Static)
            status.display = False
        except Exception as e:
            logger.warning("WhisperChannel add: %s", e)

    def toggle(self) -> None:
        self.display = not self.display
