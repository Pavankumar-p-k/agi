"""Workspace provider: desktop state inspection (snapshot/clipboard/processes).

Completed from the committed contract in tests/unit/test_workspace_provider.py.

Reuses the real desktop-state infrastructure:
- ``core.workspace.desktop_state.DesktopState`` — window/process/screenshot
  snapshot (no parallel implementation).
- ``core.workspace.clipboard_manager.ClipboardManager`` — clipboard access.

Read-only inspection only: this provider never mutates the desktop.  Actions
that would change system state belong to the desktop specialist, not here.
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
}


class WorkspaceProvider(ExecutionProvider):
    """Read-only desktop-state inspection over the existing workspace stack."""

    provider_id = "workspace"
    name = "Workspace"
    version = "1.0"
    priority = 60
    installed = True

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
            from core.workspace.desktop_state import DesktopState

            state = self._get_state()
            snap = await state.snapshot()
            status = (
                ProviderHealthStatus.HEALTHY
                if (snap.screen_width or snap.windows or snap.processes)
                else ProviderHealthStatus.DEGRADED
            )
            return self._cache_health(
                ProviderHealth(
                    status=status,
                    error=f"{len(snap.windows)} windows, {len(snap.processes)} processes",
                )
            )
        except Exception as exc:
            logger.debug("[workspace_provider] health probe failed: %s", exc)
            return self._cache_health(
                ProviderHealth(status=ProviderHealthStatus.DEGRADED, error=str(exc))
            )

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

    # -- execution -----------------------------------------------------------

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
                return self._system_stats()
            return ExecutionResult(
                success=False, output="", error=f"unknown action: {action!r}"
            )
        except Exception as exc:
            logger.debug("[workspace_provider] action %s failed: %s", action, exc)
            return ExecutionResult(success=False, output="", error=str(exc))

    async def handle_tool(self, tool_name: str, args: str) -> Optional[ExecutionResult]:
        """Tool-broker entry point: route known workspace tools, else None."""
        action = _TOOL_ACTIONS.get(tool_name)
        if action is None:
            return None
        return await self.execute({"action": action})

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 10.0

    # -- actions ---------------------------------------------------------------

    async def _snapshot(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        lines = ["Desktop Snapshot", "=" * 16]
        if snap.active_window is not None:
            aw = snap.active_window
            lines.append(f"Active window: {aw.title}")
        lines.append(f"Windows: {len(snap.windows)}")
        lines.append(f"Screen: {snap.screen_width}x{snap.screen_height}")
        lines.append(f"Mouse: ({snap.mouse_x}, {snap.mouse_y})")
        return ExecutionResult(success=True, output="\n".join(lines))

    async def _active_window(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        if snap.active_window is not None:
            aw = snap.active_window
            return ExecutionResult(
                success=True,
                output=aw.title,
                exit_code=0,
                artifacts={
                    "title": aw.title,
                    "left": aw.left,
                    "top": aw.top,
                    "width": aw.width,
                    "height": aw.height,
                },
            )
        # No active window is a legitimate observation, not an error.
        return ExecutionResult(success=True, output="", exit_code=1)

    def _clipboard_text(self) -> ExecutionResult:
        text = self._get_clipboard().get_text()
        return ExecutionResult(success=True, output=str(text or ""))

    async def _processes(self) -> ExecutionResult:
        snap = await self._get_state().snapshot()
        lines = ["Processes", "=" * 9]
        for proc in snap.processes:
            lines.append(f"{proc.pid:>8}  {proc.name}  [{proc.status}]")
        return ExecutionResult(success=True, output="\n".join(lines))

    def _system_stats(self) -> ExecutionResult:
        import psutil

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\" if psutil.WINDOWS else "/")
        lines = [
            "System Stats",
            "=" * 12,
            f"CPU: {cpu:.1f}%",
            f"Memory: {mem.percent:.1f}% used ({mem.available // (1024**2)} MB free)",
            f"Disk: {disk.percent:.1f}% used",
        ]
        return ExecutionResult(success=True, output="\n".join(lines))
