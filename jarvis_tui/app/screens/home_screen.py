from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.widgets import Label, Static, Markdown
from jarvis_tui.app.screens.base_screen import JarvisScreen
from jarvis_tui.app.widgets.hero_banner import HeroBanner

logger = logging.getLogger(__name__)


class HomeScreen(JarvisScreen):
    """
    JARVIS Home Screen.
    """
    def compose_main(self) -> ComposeResult:
        yield HeroBanner(id="hero-banner")
        yield Static("", id="system-status")
        yield Markdown("""
# Welcome to JARVIS

JARVIS is your AI Operating System. 

Use the navigation on the left to explore:
* **Chat**: Interact with the AI OS orchestrator.
* **Models**: Manage local and cloud LLMs.
* **Agents**: Monitor and deploy autonomous agents.
* **Integrations**: Connect Gmail, Telegram, WhatsApp, and more.
* **Diagnostics**: Check system health and performance.

### System Status
        """)

    async def on_mount(self) -> None:
        await self.refresh_status()

    async def refresh_status(self) -> None:
        try:
            status = await self.app.jarvis_client.get_status()
            label = self.query_one("#system-status", Static)
            healthy = status.get("healthy", status.get("status", "")) 
            if healthy in (True, "healthy", "ok", "running"):
                label.update("[bold green]● SYSTEM HEALTHY — All systems nominal[/bold green]")
            else:
                label.update(f"[bold red]● SYSTEM DEGRADED — {healthy}[/bold red]")
        except Exception as e:
            logger.warning("refresh_status backend error: %s", e)
            label = self.query_one("#system-status", Static)
            label.update("[bold red]● SYSTEM OFFLINE — Cannot reach backend[/bold red]")
