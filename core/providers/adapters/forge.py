from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)
from core.sub_agents.agents.forge import ForgeAgent as ForgeSubAgent

logger = logging.getLogger(__name__)


class ForgeProvider(ExecutionProvider):
    provider_id = "forge"
    name = "Forge"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "coding",
                "codegen",
                "generate code",
                "implement",
                "refactor",
                "debug code",
                "build",
                "compile",
                "create",
                "develop",
                "make",
                "test",
                "testing",
                "validate",
                "verify",
                "check",
            ],
            languages=["python", "java", "kotlin", "javascript", "typescript", "rust", "go"],
            frameworks=["android", "spring", "react", "django", "flask", "fastapi"],
            features=["scaffold", "modify", "repair", "test_generation"],
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.HEALTHY,
            latency_ms=0.0,
            last_checked=time.time(),
        )

    _FORGE_TOOLS = frozenset({
        "bash", "python", "write_file", "edit_file", "read_file",
        "glob", "grep", "build_project", "repair_project", "run_tests",
        "create_document", "update_document",
    })

    async def handle_tool(
        self, tool_type: str, content: str, **kwargs: Any,
    ) -> ExecutionResult | None:
        if tool_type not in self._FORGE_TOOLS:
            return None
        from core.tools.execution import execute_tool_block
        from core.tools._constants import ToolBlock
        block = ToolBlock(tool_type=tool_type, content=content)
        try:
            _desc, result = await execute_tool_block(
                block, session_id=kwargs.get("session_id", ""),
            )
            success = result.get("success", result.get("exit_code", 0) == 0 if "exit_code" in result else True)
            output = str(result.get("output", result.get("stdout", result.get("results", ""))))
            error = result.get("error", "") or result.get("stderr", "")
            return ExecutionResult(
                success=success,
                output=output[:10000],
                error=error,
                exit_code=result.get("exit_code", 0),
                metadata={"provider": "forge", "tool_type": tool_type},
            )
        except Exception as e:
            return ExecutionResult(
                success=False, output="", error=str(e), exit_code=1,
                metadata={"provider": "forge", "tool_type": tool_type},
            )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        goal = task.get("goal", "")
        mode = task.get("mode", "generate")
        start = time.monotonic()

        try:
            agent = ForgeSubAgent()
            import asyncio
            result = await asyncio.wait_for(
                agent.run(goal, mode),
                timeout=task.get("timeout", 120),
            )
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=result.success,
                output=result.output,
                exit_code=0 if result.success else 1,
                duration_ms=elapsed,
                artifacts=result.to_dict() if hasattr(result, "to_dict") else {},
                metadata={"mode": mode, "provider": "forge"},
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[ForgeProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"mode": mode, "provider": "forge"},
            )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 0.0
