from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class WorkspaceProvider(ExecutionProvider):
    provider_id = "workspace"
    name = "Workspace Awareness"
    version = "1.0.0"
    priority = 10
    installed = True

    def __init__(self) -> None:
        super().__init__()
        self._desktop_state: object | None = None

    def _get_desktop(self):
        if self._desktop_state is None:
            from core.workspace.desktop_state import DesktopState
            self._desktop_state = DesktopState()
        return self._desktop_state

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "workspace",
                "desktop_state",
                "active_window",
                "clipboard",
                "process_info",
                "system_stats",
                "browser_awareness",
                "window_detection",
                "process_monitoring",
            ],
            features=[
                "active_window_detection",
                "clipboard_read_write",
                "process_listing",
                "system_resource_monitoring",
                "browser_observation",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            dt = self._get_desktop()
            snapshot = await dt.snapshot()
            if snapshot is not None:
                return ProviderHealth(
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=0.0,
                    last_checked=time.time(),
                )
        except Exception as e:
            logger.debug("[WorkspaceProvider] Health check failed: %s", e)
        return ProviderHealth(
            status=ProviderHealthStatus.DEGRADED,
            error="Desktop state unavailable",
            last_checked=time.time(),
        )

    async def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> ExecutionResult:
        start = time.monotonic()
        action = task.get("action", task.get("capability", "snapshot"))
        session_id = task.get("session_id", "")
        dt = self._get_desktop()

        try:
            if action == "snapshot":
                snapshot = await dt.snapshot(session_id=session_id)
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    success=True,
                    output=_snapshot_to_text(snapshot),
                    exit_code=0,
                    duration_ms=elapsed,
                    metadata={"provider": "workspace", "action": "snapshot"},
                )
            elif action == "active_window":
                w = dt.window_detector.get_active_window()
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    success=w is not None,
                    output=str(w) if w else "No active window",
                    exit_code=0 if w else 1,
                    duration_ms=elapsed,
                    metadata={"provider": "workspace", "action": "active_window"},
                )
            elif action == "clipboard":
                text = dt.clipboard.get_text()
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    success=True,
                    output=text[:5000],
                    exit_code=0,
                    duration_ms=elapsed,
                    metadata={"provider": "workspace", "action": "clipboard"},
                )
            elif action == "processes":
                filter_name = task.get("filter", "")
                procs = dt.process_monitor.list_processes(filter_name=filter_name)
                elapsed = (time.monotonic() - start) * 1000
                lines = [f"{p.pid:>6}  {p.name:<30}  {p.cpu_percent:>5.1f}%  {p.memory_mb:>6.1f}MB  {p.status}" for p in procs[:100]]
                return ExecutionResult(
                    success=True,
                    output=f"Processes ({len(procs)} total):\n" + "\n".join(lines),
                    exit_code=0,
                    duration_ms=elapsed,
                    metadata={"provider": "workspace", "action": "processes", "count": len(procs)},
                )
            elif action == "system_stats":
                stats = dt.process_monitor.get_system_stats()
                elapsed = (time.monotonic() - start) * 1000
                lines = [f"{k}: {v}" for k, v in stats.items()]
                return ExecutionResult(
                    success=True,
                    output="System Stats:\n" + "\n".join(lines),
                    exit_code=0,
                    duration_ms=elapsed,
                    metadata={"provider": "workspace", "action": "system_stats"},
                )
            else:
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Unknown workspace action: {action}",
                    exit_code=1,
                    duration_ms=elapsed,
                    metadata={"provider": "workspace"},
                )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[WorkspaceProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False, output="", error=str(e), exit_code=1,
                duration_ms=elapsed, metadata={"provider": "workspace"},
            )

    async def handle_tool(
        self, tool_type: str, content: str, **kwargs: Any,
    ) -> ExecutionResult | None:
        if not tool_type.startswith("workspace_"):
            return None
        action_map = {
            "workspace_snapshot": "snapshot",
            "workspace_active_window": "active_window",
            "workspace_clipboard": "clipboard",
            "workspace_processes": "processes",
            "workspace_system_stats": "system_stats",
        }
        action = action_map.get(tool_type)
        if action is None:
            return None
        return await self.execute({"action": action, **kwargs})

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 10.0


def _snapshot_to_text(snapshot) -> str:
    lines = []
    lines.append("=== Desktop Snapshot ===")
    aw = snapshot.active_window
    if aw:
        lines.append(f"Active Window: {aw.title} ({aw.width}x{aw.height} @ {aw.left},{aw.top})")
    lines.append(f"Open Windows: {len(snapshot.windows)}")
    lines.append(f"Browser: {snapshot.browser.url or 'not active'}")
    if snapshot.browser.tabs:
        lines.append(f"Browser Tabs ({snapshot.browser.tab_count}):")
        for t in snapshot.browser.tabs[:10]:
            lines.append(f"  [{t.index}] {t.title or t.url}")
    clip = snapshot.clipboard_text
    if clip:
        lines.append(f"Clipboard: {clip[:120]}...")
    lines.append(f"Processes: {len(snapshot.processes)}")
    if snapshot.system_stats:
        lines.append(f"CPU: {snapshot.system_stats.get('cpu_percent', '?')}% | "
                      f"Mem: {snapshot.system_stats.get('memory_percent', '?')}%")
    return "\n".join(lines)
