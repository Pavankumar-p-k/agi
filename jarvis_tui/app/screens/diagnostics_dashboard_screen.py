from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Static, Button, DataTable
from jarvis_tui.app.screens.base_screen import JarvisScreen

COMPONENT_LABELS = {
    "models": "MODELS",
    "integrations": "INTEGRATIONS",
    "voice": "VOICE",
    "features": "FEATURES",
    "environment": "ENVIRONMENT",
    "system": "SYSTEM",
}

class DiagnosticsDashboardScreen(JarvisScreen):
    """
    TUI Diagnostics Dashboard UI.
    """
    def compose_main(self) -> ComposeResult:
        yield Label("# DIAGNOSTICS", id="screen-title")
        yield Label("System health and performance audit.")
        
        yield Label("## SYSTEM ENVIRONMENT")
        yield DataTable(id="env-table")
        
        yield Label("## COMPONENT HEALTH")
        yield DataTable(id="health-table")
        
        with Horizontal(id="diag-actions"):
            yield Button("Run Full Audit", id="btn-audit", variant="primary")

    async def on_mount(self) -> None:
        e_table = self.query_one("#env-table", DataTable)
        e_table.add_columns("Metric", "Value")
        
        h_table = self.query_one("#health-table", DataTable)
        h_table.add_columns("Component", "Status", "Message")
        
        await self.refresh_diagnostics()

    async def refresh_diagnostics(self) -> None:
        try:
            data = await self.app.jarvis_client.get_diagnostics()
            diag_data = data.get("data", {})
            healthy = data.get("healthy", False)
            
            e_table = self.query_one("#env-table", DataTable)
            e_table.clear()
            env = diag_data.get("environment", {})
            e_table.add_row("Disk Free", f"{env.get('disk_free_gb', 'N/A')} GB")
            e_table.add_row("Memory Free", f"{env.get('memory_free_mb', 'N/A')} MB")
            e_table.add_row("Ollama", "ONLINE" if env.get("ollama_available") else "OFFLINE")
            e_table.add_row("Network", "REACHABLE" if env.get("network_reachable") else "UNREACHABLE")
            sys_info = diag_data.get("system", {})
            if sys_info:
                e_table.add_row("Uptime", f"{sys_info.get('uptime_seconds', 'N/A')}s")
                e_table.add_row("Platform", sys_info.get("platform", "N/A"))
            
            h_table = self.query_one("#health-table", DataTable)
            h_table.clear()
            h_table.add_row("CORE", "💚 HEALTHY" if healthy else "❤️ DEGRADED", "All nominal" if healthy else "Some subsystems reporting errors")
            
            models = diag_data.get("models", {})
            models_healthy = all(m.get("healthy", False) for m in (models.values() if isinstance(models, dict) else models))
            h_table.add_row(
                "MODELS",
                "💚 HEALTHY" if models_healthy else "❤️ DEGRADED",
                f"{len(models.values() if isinstance(models, dict) else models)} provider(s) verified" if models else "No model data"
            )
            
            integrations = diag_data.get("integrations", {})
            if isinstance(integrations, dict):
                connected = sum(1 for v in integrations.values() if isinstance(v, dict) and v.get("connected", v.get("healthy", False)))
                total = len(integrations)
                int_status = "💚 HEALTHY" if connected == total else "💛 WARNING" if connected > 0 else "❤️ DEGRADED"
                int_msg = f"{connected}/{total} connected"
            elif isinstance(integrations, list):
                int_status = "💚 HEALTHY" if integrations else "💛 WARNING"
                int_msg = f"{len(integrations)} integration(s)"
            else:
                int_status = "—"
                int_msg = str(integrations) if integrations else "No integration data"
            h_table.add_row("INTEGRATIONS", int_status, int_msg)
            
            voice = diag_data.get("voice", {})
            if voice:
                v_ok = voice.get("stt_available", False) or voice.get("tts_available", False) or voice.get("wake_word_available", False)
                h_table.add_row(
                    "VOICE",
                    "💚 HEALTHY" if v_ok else "❤️ DEGRADED",
                    f"STT={'✓' if voice.get('stt_available') else '✗'} TTS={'✓' if voice.get('tts_available') else '✗'} Wake={'✓' if voice.get('wake_word_available') else '✗'}"
                )
            
        except Exception as e:
            self.app.notify(f"Error fetching diagnostics: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-audit":
            await self.refresh_diagnostics()
            self.app.notify("Full audit completed.", severity="success")
