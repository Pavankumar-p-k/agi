from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from typing import Any, AsyncIterator

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)

_CODEX_CMD = "codex"


class CodexProvider(ExecutionProvider):
    provider_id = "codex"
    name = "Codex CLI"
    version = "1.0.0"
    priority = 60
    installed = bool(shutil.which(_CODEX_CMD))

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "coding",
                "codegen",
                "implement",
                "scaffold",
                "new_file",
            ],
            languages=["python", "java", "kotlin", "javascript", "typescript"],
            frameworks=[],
            features=["scaffold", "generate"],
        )

    async def health(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                _CODEX_CMD, "--version",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            elapsed = (time.monotonic() - start) * 1000
            if proc.returncode == 0:
                return ProviderHealth(
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=elapsed,
                    last_checked=time.time(),
                )
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=f"exit {proc.returncode}",
                last_checked=time.time(),
            )
        except FileNotFoundError:
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error="codex CLI not found",
                last_checked=time.time(),
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=str(e)[:80],
                last_checked=time.time(),
            )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        goal = task.get("goal", "")
        cwd = task.get("cwd", os.getcwd())
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                _CODEX_CMD, goal,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=task.get("timeout", 120)
            )
            elapsed = (time.monotonic() - start) * 1000
            output = stdout.decode(errors="replace")
            err_text = stderr.decode(errors="replace")[:200]

            return ExecutionResult(
                success=proc.returncode == 0,
                output=output,
                error=err_text,
                exit_code=proc.returncode or 0,
                duration_ms=elapsed,
                metadata={"provider": "codex"},
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False,
                output="",
                error="timeout",
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "codex"},
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[Codex] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "codex"},
            )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.02

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 20_000
