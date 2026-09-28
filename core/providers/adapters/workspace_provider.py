"""WorkspaceProvider — read-only workspace awareness as a provider.

Gate 8: this provider is awareness-only. It never touches the desktop
control layer — it composes the core.workspace observation modules
instead, so awareness and control stay separate packages.
"""
from __future__ import annotations

import asyncio
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)


class WorkspaceProvider(ExecutionProvider):
    """Exposes workspace snapshot actions through the provider contract."""

    provider_id = "workspace"
    name = "Workspace Awareness"
    version = "1.0.0"
    priority = 55

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["workspace", "desktop_state"],
            version=self.version,
            features=["snapshot", "processes", "clipboard", "windows"],
            languages=[],
            modalities=["workspace"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.HEALTHY,
                              detail="workspace awareness ready")

    async def estimate_cost(self, task: dict) -> float:
        return 0.0

    async def estimate_latency(self, task: dict) -> float:
        return 10.0

    async def handle_tool(self, tool: str, args: str):
        """Tool-call entry point; None for tools this provider does not own."""
        mapping = {
            "workspace_snapshot": "snapshot",
        }
        action = mapping.get(str(tool))
        if action is None:
            return None
        return await self.execute({"action": action})

    async def execute(self, task: dict, context: Any = None) -> ExecutionResult:
        task = dict(task or {})
        action = str(task.get("action", "")).strip()

        if action == "snapshot":
            return await self._snapshot()
        if action == "active_window":
            return self._active_window()
        if action == "clipboard":
            return self._clipboard()
        if action == "processes":
            return self._processes()
        if action == "system_stats":
            return self._system_stats()
        return ExecutionResult(
            success=False,
            error=f"Unknown workspace action: {action!r}",
            provider_id=self.provider_id,
        )

    # ── actions ──────────────────────────────────────────────────────
    async def _snapshot(self) -> ExecutionResult:
        from core.workspace.desktop_state import DesktopState
        snap = await DesktopState().snapshot()
        lines = [
            "Desktop Snapshot",
            f"active_window: {snap.active_window or 'unknown'}",
            f"windows: {len(snap.windows)}",
            f"browser: {snap.browser.get('browser_name') or 'none'} "
            f"(tabs={snap.browser.get('tab_count', 0)})",
            f"clipboard: {'set' if snap.clipboard_text else 'empty'}",
            f"processes: {len(snap.processes)}",
        ]
        stats = snap.system_stats or {}
        if stats.get("available"):
            lines.append(f"cpu: {stats.get('cpu_percent')}%  "
                         f"ram: {stats.get('ram_percent')}%")
        return ExecutionResult(success=True, output="\n".join(lines),
                               provider_id=self.provider_id,
                               metadata={"snapshot": snap.__dict__})

    def _active_window(self) -> ExecutionResult:
        from core.workspace.window_detector import WindowDetector
        window = WindowDetector().get_active_window()
        if window is None:
            return ExecutionResult(success=True, output="no active window",
                                   exit_code=1, provider_id=self.provider_id)
        return ExecutionResult(
            success=True, output=str(getattr(window, "title", "")),
            exit_code=0, provider_id=self.provider_id)

    def _clipboard(self) -> ExecutionResult:
        from core.workspace.clipboard_manager import ClipboardManager
        manager = ClipboardManager()
        if not manager.is_available():
            return ExecutionResult(
                success=True, output="clipboard unavailable",
                provider_id=self.provider_id)
        text = manager.get_text()
        return ExecutionResult(success=True,
                               output=text[:2000] or "(empty)",
                               provider_id=self.provider_id)

    def _processes(self) -> ExecutionResult:
        from core.workspace.process_monitor import ProcessMonitor
        procs = ProcessMonitor().list_processes()
        names = [p.get("name", "") for p in procs[:50]]
        return ExecutionResult(
            success=True,
            output=f"Processes ({len(procs)}): " + ", ".join(n for n in names if n),
            provider_id=self.provider_id)

    def _system_stats(self) -> ExecutionResult:
        from core.workspace.process_monitor import ProcessMonitor
        stats = ProcessMonitor().get_system_stats()
        if not stats.get("available"):
            return ExecutionResult(
                success=True, output="System Stats: unavailable",
                provider_id=self.provider_id)
        return ExecutionResult(
            success=True,
            output=(f"System Stats: CPU {stats.get('cpu_percent')}% | "
                    f"RAM {stats.get('ram_percent')}% "
                    f"({stats.get('ram_used_gb')}GB/"
                    f"{stats.get('ram_total_gb')}GB)"),
            provider_id=self.provider_id)


workspace_provider = WorkspaceProvider()


__all__ = ["WorkspaceProvider", "workspace_provider"]
