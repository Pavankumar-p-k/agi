"""GitHubProvider: git/GitHub operations as a capability provider.

Completed from the committed contract in tests/unit/test_github_provider.py.
Execution shells out to the existing git CLI (read-only status by default);
anything that mutates repository state must go through the existing approval
gates — this adapter never grants itself new authority.
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

_READ_ONLY_ACTIONS = {"status", "log", "diff", "branch_list"}


class GitHubProvider(ExecutionProvider):
    provider_id = "github"
    name = "GitHub"
    version = "1.0.0"
    priority = 80
    installed = True
    _enabled = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capability_names=["github", "git", "version_control"])

    async def health(self) -> ProviderHealth:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            status = ProviderHealthStatus.HEALTHY if proc.returncode == 0 \
                else ProviderHealthStatus.DEGRADED
        except Exception as exc:
            return self._cache_health(ProviderHealth(
                status=ProviderHealthStatus.DEGRADED, error=str(exc),
            ))
        return self._cache_health(ProviderHealth(status=status))

    async def execute(
        self, task: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        start = time.time()
        action = str(task.get("action", "") or "")
        if action not in _READ_ONLY_ACTIONS:
            return ExecutionResult(success=False, error=f"Unknown github action: {action}")
        args = ["git", action.replace("branch_list", "branch")]
        if action == "branch_list":
            args.append("--list")
        cwd = task.get("cwd")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
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
                exit_code=1,
                duration_ms=round((time.time() - start) * 1000.0, 3),
            )

    async def handle_tool(self, tool_name: str, content: str, **kwargs: Any) -> Optional[Any]:
        """Adapter boundary hook: route github tools to this provider."""
        if not tool_name.startswith("github_"):
            return None
        action = tool_name.removeprefix("github_")
        task = {"action": action}
        if content:
            task["message"] = content
        task.update(kwargs)
        return await self.execute(task)

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 500.0
