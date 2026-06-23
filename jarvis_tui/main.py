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

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textual.app import App

from jarvis_tui.app.screens.main_screen import MainScreen
from jarvis_tui.app.services.jarvis_client import JarvisClient
from jarvis_tui.app.services.theme_manager import ThemeManager
logger = logging.getLogger(__name__)


class JarvisApp(App):
    CSS = """
    /* Base CSS remains, but colors will be overridden by ThemeManager */
    Screen {
        background: #30302e;
        color: #f0f0f0;
    }

    #sidebar {
        width: 32;
        height: 100%;
        background: #262624;
        border-right: solid #3e3e3c;
    }

    #sidebar-container {
        padding: 0;
    }

    #sidebar-container Label {
        margin-top: 1;
        margin-left: 1;
        text-style: bold;
        color: #c2c0b6;
    }

    #nav-container Button {
        width: 100%;
        height: 3;
        border: none;
        background: transparent;
        color: #c2c0b6;
        padding: 0 2;
        margin: 0;
    }

    #nav-container Button:hover {
        background: #3e3e3c;
    }

    #nav-container Button.primary {
        background: #3e3e3c;
        color: #4a9eff;
        text-style: bold;
    }

    .selector {
        background: #30302e;
        padding: 0 1;
        border: solid #3e3e3c;
        color: #c2c0b6;
    }

    #main-content {
        width: 1fr;
        height: 100%;
    }

    #hero-banner {
        height: auto;
        min-height: 10;
        background: #262624;
        border-bottom: double #3e3e3c;
    }

    #chat-stream {
        height: 1fr;
        background: #30302e;
        overflow-y: scroll;
        padding: 1;
    }

    #input-bar {
        height: 3;
        background: #262624;
        border-top: solid #3e3e3c;
        layout: horizontal;
    }

    #input-container {
        width: 1fr;
        height: 100%;
    }

    #chat-input {
        width: 100%;
        border: none;
        background: transparent;
        color: #c2c0b6;
    }

    #ghost-label {
        color: #8e9dae;
        text-style: italic;
        padding-top: 1;
    }

    #code-badge {
        background: #4a2a4a;
        color: #ff88ff;
        text-style: bold;
        margin: 0 1;
    }

    #palette-blur {
        position: absolute;
        width: 100%;
        height: 100%;
        color: #1a1a1a;
        opacity: 0.5;
    }

    #status-bar {
        height: 1;
        background: #262624;
        color: #c2c0b6;
        dock: bottom;
    }

    #status-spacer {
        width: 1fr;
    }

    #cmd-palette {
        layer: overlay;
        width: 60;
        height: auto;
        max-height: 20;
        background: #30302e;
        border: solid #4a9eff;
        dock: top;
        margin: 4 20;
    }

    #palette-container {
        padding: 1;
    }

    #palette-list {
        height: auto;
        max-height: 15;
    }

    #confirm-gate {
        layer: overlay;
        width: 50;
        height: auto;
        background: #1e0a0a;
        border: solid #cd5c58;
        dock: bottom;
        margin: 5 25;
        padding: 1;
    }

    #confirm-container Horizontal {
        height: 3;
        margin-top: 1;
        align: center middle;
    }

    #confirm-container Button {
        margin: 0 1;
    }

    #toast-rack {
        layer: overlay;
        dock: top;
        align: right top;
        width: 30;
        height: auto;
        margin: 2;
    }

    Toast {
        background: #262624;
        border: solid #c2c0b6;
        padding: 0 1;
        margin-bottom: 1;
        color: #f0f0f0;
    }

    .whisper {
        color: #a060a0;
        text-style: italic;
        margin-top: 1;
    }

    #diff-pane {
        layer: overlay;
        dock: right;
        width: 80;
        height: 100%;
        background: #1e1e1e;
        border-left: solid #3e3e3c;
    }

    #replay-header {
        text-align: center;
        padding: 1;
        background: #262624;
        color: #4a9eff;
        text-style: bold;
    }

    #replay-container {
        height: 1fr;
        padding: 2;
        align: center middle;
    }

    #replay-controls {
        height: 3;
        padding: 0 2;
        background: #262624;
        align: center middle;
    }

    #replay-progress {
        width: 1fr;
        margin: 0 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jarvis_client = JarvisClient()

    def on_mount(self) -> None:
        self.push_screen(MainScreen())
        self.run_worker(self.monitor_events())
        self.run_worker(self.fetch_initial_state())

    async def fetch_initial_state(self) -> None:
        """Fetches models, tasks, and system status from the backend."""
        try:
            status = await self.jarvis_client.get_status()
            # Find the sidebar and update it
            try:
                sidebar = self.screen.query_one("#sidebar")
                # Read model name from /api/system/status response
                # Response: {"status":"online","ollama":"reachable","model":"ollama/llama3.1:8b",...}
                model_val = status.get("model") or status.get("ollama", "")
                if model_val and model_val not in ("unreachable", "offline", ""):
                    # Strip provider prefix for display
                    display = model_val.split("/", 1)[1] if "/" in model_val else model_val
                    sidebar.model_name = display

                # Map real memory/token usage
                mem = status.get("memory", {})
                # ... update context pct based on real data if available
            except Exception as e:
                logger.warning(f"[SWALLOWED] {e}")
        except Exception:
            # Backend not ready yet, monitor_events will handle reconnection
            logger.warning(f"[SWALLOWED] error in ./jarvis_tui/main.py")

    async def monitor_events(self) -> None:
        """Background worker to monitor JARVIS events."""
        while True:
            try:
                async for event in self.jarvis_client.stream_events():
                    # Forward event to the active screen
                    if isinstance(self.screen, MainScreen):
                        await self.handle_jarvis_event(event)
            except Exception as e:
                # Update status bar to offline
                try:
                    status = self.screen.query_one("#status-bar")
                    status.connected = False
                except Exception as e:
                    logger.warning(f"[SWALLOWED] {e}")
                # Retry after delay
                await asyncio.sleep(5.0)
                try:
                    # Attempt to reconnect
                    await self.jarvis_client.get_status()
                    status = self.screen.query_one("#status-bar")
                    status.connected = True
                except Exception as e:
                    logger.warning(f"[SWALLOWED] {e}")

    async def handle_jarvis_event(self, event: dict) -> None:
        """Routes real AI OS orchestrator events to appropriate widgets."""
        try:
            chat = self.screen.query_one("#chat-stream")
            banner = self.screen.query_one("#hero-banner")
            status = self.screen.query_one("#status-bar")
            sidebar = self.screen.query_one("#sidebar")
        except Exception:
            return

        etype = event.get("type")

        if etype == "planning":
            banner.mood = "thinking"
            goal = event.get("goal", "task")
            chat.add_message("ORACLE", f"Planning execution for goal: [bold]{goal}[/bold]", msg_type="thinking")

        elif etype == "executing":
            banner.mood = "thinking"
            step = event.get("step", {})
            tool = step.get("tool", "unknown")
            args = step.get("args", {})
            chat.add_message("SCOUT", f"{tool}({args})", msg_type="tool_call")

        elif etype == "executed":
            banner.mood = "done"
            result = event.get("result", {})
            if result.get("success"):
                chat.add_message("SYSTEM", str(result.get("output", "Success")), msg_type="tool_result")
            else:
                chat.add_message("SYSTEM", f"Error: {result.get('error')}", msg_type="error")

        elif etype == "completed":
            banner.mood = "done"
            res = event.get("success", False)
            msg = "Task completed successfully." if res else "Task finished with errors."
            chat.add_message("NEXUS", msg)

        elif etype == "error":
            banner.mood = "error"
            err = event.get("error") or event.get("reason") or "Unknown error"
            chat.add_message("SYSTEM", f"ERROR: {err}", msg_type="error")
            status.show_alert(f"⚠ ERROR: {err[:20]}...")

        elif etype == "status_update":
            # Map system stats if provided
            sidebar.context_pct = event.get("context_pct", sidebar.context_pct)
            status.latency = event.get("latency", status.latency)
            status.connected = event.get("connected", True)

    async def on_unmount(self) -> None:
        await self.jarvis_client.close()

    def switch_theme(self, theme_name: str) -> None:
        """Applies a new visual theme."""
        new_css = ThemeManager.get_css(theme_name)
        # Textual allows injecting CSS at runtime
        self.screen.styles.update(new_css)
        try:
            toast = self.screen.query_one("#toast-rack")
            toast.show_toast(f"Theme switched to {theme_name.capitalize()}", severity="success")
        except Exception as e:
            logger.warning(f"[SWALLOWED] {e}")

    def handle_navigation(self, screen_name: str) -> None:
        """Switches the current screen based on navigation selection."""
        from jarvis_tui.app.screens.home_screen import HomeScreen
        from jarvis_tui.app.screens.feature_registry_screen import FeatureRegistryScreen
        from jarvis_tui.app.screens.model_management_screen import ModelManagementScreen
        from jarvis_tui.app.screens.integration_management_screen import IntegrationManagementScreen
        from jarvis_tui.app.screens.agent_dashboard_screen import AgentDashboardScreen
        from jarvis_tui.app.screens.diagnostics_dashboard_screen import DiagnosticsDashboardScreen
        from jarvis_tui.app.screens.voice_dashboard_screen import VoiceDashboardScreen
        from jarvis_tui.app.screens.automation_dashboard_screen import AutomationDashboardScreen
        from jarvis_tui.app.screens.memory_dashboard_screen import MemoryDashboardScreen
        from jarvis_tui.app.screens.settings_screen import SettingsScreen
        from jarvis_tui.app.screens.placeholder_screen import PlaceholderScreen

        screens = {
            "home": HomeScreen,
            "chat": MainScreen,
            "registry": FeatureRegistryScreen,
            "models": ModelManagementScreen,
            "agents": AgentDashboardScreen,
            "automation": AutomationDashboardScreen,
            "integrations": IntegrationManagementScreen,
            "diagnostics": DiagnosticsDashboardScreen,
            "voice": VoiceDashboardScreen,
            "memory": MemoryDashboardScreen,
            "settings": SettingsScreen,
        }

        # Handle placeholders for now (Skills, Plugins, Projects)
        screen_class = screens.get(screen_name, lambda: PlaceholderScreen(title=screen_name.capitalize()))
        
        # Don't push if already active
        if isinstance(self.screen, screen_class):
            return
            
        self.push_screen(screen_class())

if __name__ == "__main__":
    app = JarvisApp()
    app.run()
