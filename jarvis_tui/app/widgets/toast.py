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
from textual.widget import Widget
from textual.widgets import Label, Static


class Toast(Static):
    """
    A single notification toast.
    """
    def __init__(self, message: str, severity: str = "info", timeout: float = 3.0, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.severity = severity
        self.timeout = timeout

    def compose(self) -> ComposeResult:
        icon = "ℹ"
        if self.severity == "success": icon = "✓"
        elif self.severity == "warning": icon = "⚠"
        elif self.severity == "error": icon = "✕"

        yield Label(f"{icon} {self.message}")

    def on_mount(self) -> None:
        self.set_timer(self.timeout, self.remove)

class ToastRack(Widget):
    """
    Container for stacking notification toasts.
    """
    def show_toast(self, message: str, severity: str = "info", timeout: float = 3.0) -> None:
        toast = Toast(message, severity, timeout)
        self.mount(toast)
