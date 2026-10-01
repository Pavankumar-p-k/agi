"""Workspace provider: desktop state inspection (snapshot/clipboard/processes).

Completed from the committed contract in tests/unit/test_workspace_provider.py.

Reuses the real awareness-only workspace stack:
- ``core.workspace.desktop_state.DesktopState`` — window/process snapshot.
- ``core.workspace.clipboard_manager.ClipboardManager`` — clipboard read.

Read-only inspection only: this provider never mutates the desktop (Gate 8).
Actions that change system state belong to the desktop specialist, not here.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)

__all__ = ["WorkspaceProvider"]

_TOOL_ACTIONS = {
    "workspace_snapshot": "snapshot",
    "workspace_active_window": "active_window",
    "workspace_clipboard": "clipboard",
    "workspace_processes": "processes",
    "workspace_system_stats": "system_stats",
}


class WorkspaceProvider(ExecutionProvider):
    """Read-only desktop-state inspection over the existing workspace stack."""

    provider_id = "workspace"
    name = "Workspace"
    version = "1.0"
    priority = 60
    installed = True
    _enabled = True

    def __init__(self) -> None:
        super().__init__()
        self._state: Any = None
        self._clipboard: Any = None

    # -- lifecycle ---------------------------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["workspace", "desktop_state", "clipboard"]
        )

    async def health(self) -> ProviderHealth:
        try:
            snap = await self._get_state().snapshot()
            healthy = bool(getattr(snap, "windows", None)
                           or getattr(snap, "processes", None))
            status = (ProviderHealthStatus.HEALTHY if healthy
                      else ProviderHealthStatus.DEGRADED)
            return self._cache_health(ProviderHealth(status=status))
        except Exception as exc:  # noqa: BLE001 — probe failures are data
            logger.debug("[workspace_provider] health probe failed: %s", exc)
            return self._cache_health(
                ProviderHealth(status=ProviderHealthStatus.DEGRADED, error=str(exc)))

    def _get_state(self) -> Any:
        if self._state is None:
            from core.workspace.desktop_state import DesktopState
            self._state = DesktopState()
        return self._state

    def _get_clipboard(self) -> Any:
        if self._clipboard is None:
            from core.workspace.clipboard_manager import ClipboardManager
            self._clipboard = ClipboardManager()
        return self._clipboard

    # -- execution ---------------------------------------------------------

    async def execute(
        self, task: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        action = str((task or {}).get("action", "") or "")
        try:
            if action == "snapshot":
                return await self._snapshot()
            if action == "active_window":
                return await self._active_window()
            if action == "clipboard":
                return self._clipboard_text()
            if action == "processes":
                return await self._processes()
            if action == "system_stats":
                return await self._system_stats()
            return ExecutionResult(
                success=False, output="", error=f"unknown action: {action!r}")
        except Exception as exc:  # noqa: BLE001 — honest failure, never raise
            logger.debug("[workspace_provider] action %s failed: %s", action, exc)
            return ExecutionResult(success=False, output="", error=str(exc))

    async def handle_tool(
        self, tool_name: str, args: str = "", **kwargs: Any
    ) -> Optional[ExecutionResult]:
        """Tool-broker entry point: route known workspace tools, else None."""
        action = _TOOL_ACTIONS.get(tool_name)
        if action is None:
            return None
        return await self.execute({"action": action})

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 10.0

    # -- actions -----------------------------------------------------------

    async def _snapshot(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        lines = ["Desktop Snapshot", "=" * 16]
        active = getattr(snap, "active_window", None)
        if active is not None:
            title = getattr(active, "title", None) or str(active)
            lines.append(f"Active window: {title}")
        windows = list(getattr(snap, "windows", []) or [])
        lines.append(f"Windows: {len(windows)}")
        lines.append(f"Clipboard: {str(getattr(snap, 'clipboard_text', '') or '')[:80]}")
        lines.append(f"Processes: {len(getattr(snap, 'processes', []) or [])}")
        return ExecutionResult(success=True, output="\n".join(lines))

    async def _active_window(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        active = getattr(snap, "active_window", None)
        if active is not None:
            title = getattr(active, "title", None) or str(active)
            return ExecutionResult(success=True, output=str(title), exit_code=0)
        # No active window is a legitimate observation, not an error.
        return ExecutionResult(success=True, output="", exit_code=1)

    def _clipboard_text(self) -> ExecutionResult:
        text = self._get_clipboard().get_text()
        return ExecutionResult(success=True, output=str(text or ""))

    async def _processes(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        lines = ["Processes", "=" * 9]
        for proc in list(getattr(snap, "processes", []) or []):
            if isinstance(proc, dict):
                pid = proc.get("pid", "")
                name = proc.get("name", "")
            else:
                pid = getattr(proc, "pid", "")
                name = getattr(proc, "name", "")
            lines.append(f"{pid:>8}  {name}")
        return ExecutionResult(success=True, output="\n".join(lines))

    async def _system_stats(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        stats = dict(getattr(snap, "system_stats", None) or {})
        if not stats.get("available", bool(stats)):
            return ExecutionResult(success=True, output="System Stats: unavailable")
        lines = [
            "System Stats",
            "=" * 12,
            f"CPU: {stats.get('cpu_percent', 0)}%",
            f"RAM: {stats.get('ram_percent', 0)}% "
            f"({stats.get('ram_used_gb', 0)}GB/{stats.get('ram_total_gb', 0)}GB)",
        ]
        return ExecutionResult(success=True, output="\n".join(lines))
