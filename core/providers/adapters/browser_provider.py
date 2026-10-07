"""BrowserProvider — exposes the Playwright browser stack as a provider.

Gate alignment: the browser is just another capability provider. This adapter
maps task dicts onto the session-scoped browser tools in
``core.tools.browser_tools`` (verified navigation, snapshot-before-act) and
reports honest results. It never spawns a browser implicitly: without a
browser stack the health probe reports DOWN and execute fails with a clear
error instead of blocking on a cold launch.
"""
from __future__ import annotations

import importlib.util
import time
from typing import Any, Callable, Optional

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

# action name -> browser_tools.do_<action> (1:1 with the tool layer).
_ACTIONS = (
    "navigate", "get_url", "get_title", "snapshot", "a11y_tree",
    "find", "find_interactive", "click", "fill", "press", "select",
    "scroll", "upload", "extract", "form_fill", "search",
    "wait_visible", "wait_text", "wait_state", "is_visible",
    "screenshot", "refresh", "go_back", "current_state",
    "list_tabs", "new_tab", "switch_tab", "health",
)


def _playwright_available() -> bool:
    try:
        return importlib.util.find_spec("playwright") is not None
    except Exception:  # noqa: BLE001 — probe must never raise
        return False


class BrowserProvider(ExecutionProvider):
    """Drives the core browser stack through the standard provider contract."""

    provider_id = "browser"
    name = "Browser Controller"
    version = "1.0.0"
    priority = 50

    def __init__(self) -> None:
        super().__init__()

    @property
    def installed(self) -> bool:
        """The browser stack needs Playwright importable on this machine."""
        return _playwright_available()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["browser"],
            features=["navigate", "snapshot", "click", "fill", "extract",
                      "search", "tabs", "screenshot"],
            languages=[],
        )

    async def health(self) -> ProviderHealth:
        if not self.installed:
            return self._cache_health(ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error="playwright is not installed",
            ))
        try:
            from core.browser_manager import BrowserManager
            manager = BrowserManager.instance()
        except Exception as exc:  # noqa: BLE001 — backend errors surface honestly
            return self._cache_health(ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=f"{type(exc).__name__}: {exc}",
            ))
        if not manager.started:
            # Stack present but never launched: not down, just cold.
            return self._cache_health(ProviderHealth(
                status=ProviderHealthStatus.UNKNOWN,
                error="no browser sessions started yet",
            ))
        return self._cache_health(ProviderHealth(
            status=ProviderHealthStatus.HEALTHY,
        ))

    async def execute(
        self, task: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start = time.time()
        task = dict(task or {})
        action = str(task.get("action", "")).strip()

        if not action:
            return ExecutionResult(
                success=False,
                error="missing 'action' in browser task",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
        if action not in _ACTIONS:
            return ExecutionResult(
                success=False,
                error=f"Unknown browser action: {action!r}",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
        if not self.installed:
            return ExecutionResult(
                success=False,
                error="browser stack unavailable: playwright is not installed",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )

        try:
            from core.tools import browser_tools as bt
            handler: Callable[..., dict[str, Any]] = getattr(bt, f"do_browser_{action}")
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                success=False,
                error=f"browser tool layer unavailable: {type(exc).__name__}: {exc}",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )

        session_id = str(task.get("session_id", "default"))
        kwargs = {k: v for k, v in task.items() if k not in ("action", "session_id")}
        try:
            result = await handler(session_id=session_id, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )

        ok = isinstance(result, dict) and result.get("status") == "ok"
        return ExecutionResult(
            success=bool(ok),
            output="" if result.get("result") is None else str(result.get("result")),
            error=None if ok else str(result.get("error", "browser tool failed")),
            duration_ms=round((time.time() - start) * 1000.0, 3),
            metadata={
                "session_id": session_id,
                "action": action,
                "error_type": result.get("error_type"),
            },
        )


__all__ = ["BrowserProvider"]
