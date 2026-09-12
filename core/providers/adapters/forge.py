"""ForgeProvider: the internal coding agent as a capability provider.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py
(TestForgeProvider).  Delegates execution to the existing Forge agent backend
(``core.agents.forge.ForgeAgent``) — no parallel agent implementation.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class ForgeSubAgent:
    """Thin wrapper over the Forge agent backend.

    Kept as a separate small class so tests can patch
    ``core.providers.adapters.forge.ForgeSubAgent`` without touching the
    underlying agent machinery.  The backend is resolved lazily at first use:
    the canonical ``core.agents.forge.ForgeAgent`` when present, else the
    compatibility path under ``core.agents._legacy.forge``.
    """

    def __init__(self) -> None:
        try:
            from core.agents.forge import ForgeAgent  # canonical backend
        except Exception:
            from core.agents._legacy.forge import ForgeAgent  # compat path
        self._agent = ForgeAgent()

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        result = self._agent.run(task)
        if asyncio.iscoroutine(result):
            result = await result
        return result


class ForgeProvider(ExecutionProvider):
    """Internal coding provider (highest priority, always installed)."""

    provider_id = "forge"
    name = "Forge"
    version = "1.0.0"
    priority = 10
    installed = True
    _enabled = True

    def __init__(self) -> None:
        super().__init__()
        self._agent: Optional[ForgeSubAgent] = None

    def _get_agent(self) -> ForgeSubAgent:
        if self._agent is None:
            self._agent = ForgeSubAgent()
        return self._agent

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["coding", "python", "testing", "review", "refactoring"],
            languages=["python", "javascript", "typescript"],
            frameworks=["fastapi", "django", "react"],
        )

    async def health(self) -> ProviderHealth:
        # Forge is the built-in internal provider: it is healthy whenever the
        # provider class itself is importable (the backend resolves lazily at
        # execute time and reports honest failures).
        return self._cache_health(ProviderHealth(
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=0.0,
        ))

    async def execute(
        self, task: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start = time.time()
        try:
            agent = self._get_agent()
            payload = dict(task)
            if context:
                payload["context"] = context
            result = await agent.run(payload)
            output = ""
            if isinstance(result, dict):
                output = str(result.get("output", "") or result.get("result", ""))
            elif result is not None:
                output = str(result)
            return ExecutionResult(
                success=True,
                output=output,
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
