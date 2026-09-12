"""CodexProvider: external Codex CLI as a capability provider.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py
(TestExternalProviders).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
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

_CLI = "codex"


class CodexProvider(ExecutionProvider):
    provider_id = "codex"
    name = "Codex CLI"
    version = "1.0.0"
    priority = 70

    def __init__(self) -> None:
        super().__init__()

    @property
    def installed(self) -> bool:
        """Detected live from PATH (class attr when patched by tests)."""
        return shutil.which(_CLI) is not None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=["coding", "scaffold", "review", "testing"],
            languages=["python", "javascript", "typescript"],
        )

    async def health(self) -> ProviderHealth:
        if not self.installed:
            return self._cache_health(ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error="codex CLI not found on PATH",
            ))
        return self._cache_health(ProviderHealth(status=ProviderHealthStatus.HEALTHY))

    async def execute(
        self, task: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start = time.time()
        if not self.installed:
            return ExecutionResult(
                success=False,
                error="codex CLI not installed",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
        goal = str(task.get("goal", "") or "")
        cmd = [_CLI, "exec", goal] if goal else [_CLI, "--version"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            except asyncio.TimeoutError:
                proc.kill()
                return ExecutionResult(
                    success=False,
                    error="codex CLI timed out",
                    duration_ms=round((time.time() - start) * 1000.0, 3),
                )
            output = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()
            return ExecutionResult(
                success=proc.returncode == 0,
                output=output,
                error=err or None,
                exit_code=proc.returncode,
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )
