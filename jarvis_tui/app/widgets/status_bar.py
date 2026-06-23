from __future__ import annotations

import logging
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

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label
logger = logging.getLogger(__name__)


class StatusBar(Widget):
    """
    Bottom status bar with session info and system metrics.
    """
    session_id = reactive("none")
    tokens = reactive("0")
    latency = reactive(0)
    agents_count = reactive(0)
    git_branch = reactive("...")
    alert_msg = reactive("")
    connected = reactive(False)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(" session:-- ", id="status-session")
            yield Label(" tokens:0 ", id="status-tokens")
            yield Label(" latency:--ms ", id="status-latency")
            yield Label(" agents:0 ", id="status-agents")
            yield Label(" git:-- ", id="status-git")
            yield Label("", id="status-alert")
            yield Label("", id="status-spacer")
            yield Label("●", id="status-health")
            yield Label(datetime.now().strftime("%H:%M:%S"), id="status-time")

    def watch_session_id(self, val: str) -> None:
        try: self.query_one("#status-session", Label).update(f" session:{val} ")
        except Exception as e:
            logger.warning(f"[SWALLOWED] {e}")

    def watch_tokens(self, val: str) -> None:
        try: self.query_one("#status-tokens", Label).update(f" tokens:{val} ")
        except Exception as e:
            logger.warning(f"[SWALLOWED] {e}")

    def watch_agents_count(self, val: int) -> None:
        try: self.query_one("#status-agents", Label).update(f" agents:{val} ")
        except Exception as e:
            logger.warning(f"[SWALLOWED] {e}")

    def watch_git_branch(self, val: str) -> None:
        try: self.query_one("#status-git", Label).update(f" git:{val}✓ ")
        except Exception as e:
            logger.warning(f"[SWALLOWED] {e}")

    def on_mount(self) -> None:
        self.set_interval(1.0, self.update_time)

    def update_time(self) -> None:
        self.query_one("#status-time", Label).update(datetime.now().strftime("%H:%M:%S"))

    def show_alert(self, message: str, timeout: float = 5.0) -> None:
        self.alert_msg = message
        self.set_timer(timeout, self.clear_alert)

    def clear_alert(self) -> None:
        self.alert_msg = ""

    def watch_alert_msg(self, msg: str) -> None:
        label = self.query_one("#status-alert", Label)
        label.update(f" [bold red]{msg}[/bold red] " if msg else "")

    def watch_connected(self, connected: bool) -> None:
        label = self.query_one("#status-health", Label)
        label.styles.color = "green" if connected else "red"

    def watch_latency(self, latency: int) -> None:
        try:
            label = self.query_one("#status-latency", Label)
            if latency < 500:
                label.styles.color = "#7ab948"
            elif latency < 2000:
                label.styles.color = "#d1a041"
            else:
                label.styles.color = "#ee8884"
        except Exception as e:
            logger.warning(f"[SWALLOWED] {e}")
