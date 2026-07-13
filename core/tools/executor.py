"""ToolExecutor — canonical execution wrapper for all tool calls.

Wraps ``execute_tool_block`` with ``ExecutionManager`` lifecycle events,
progress reporting, and memory recording.

Usage:
    executor = ToolExecutor()
    text, result = await executor.execute(tool_block, session_id="...")
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.tools._constants import ToolBlock
from core.tools.execution.handlers import execute_tool_block
from core.tools.resolver import ToolResolver

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Canonical tool executor with ``ExecutionManager`` lifecycle.

    Every tool call publishes started/progress/completed/failed events
    and records memory traces automatically.
    """

    def __init__(
        self,
        execution_manager: Any | None = None,
        resolver: ToolResolver | None = None,
    ) -> None:
        self._execution_manager = execution_manager
        self._resolver = resolver or ToolResolver()

    @property
    def execution_manager(self) -> ExecutionManager:
        if self._execution_manager is None:
            from core.execution import ExecutionManager
            self._execution_manager = ExecutionManager()
        return self._execution_manager

    @property
    def resolver(self) -> ToolResolver:
        return self._resolver

    async def execute(
        self,
        block: ToolBlock,
        session_id: str | None = None,
        disabled_tools: set | None = None,
        owner: str | None = None,
        progress_cb: Callable[[dict], Awaitable[None]] | None = None,
        context: Any | None = None,
    ) -> tuple[str, dict]:
        tool_name = block.tool_type if hasattr(block, "tool_type") else str(block)
        em = self.execution_manager

        exec_ctx = em.create_context(
            source=f"tool:{tool_name}",
            metadata={"tool": tool_name, "owner": owner or ""},
        )

        # Wrap progress_cb so each tool-level progress event also
        # publishes to the canonical EventBus through ExecutionManager.
        async def _bridged_progress(payload: dict) -> None:
            em.publish_progress(
                exec_ctx, f"tool_progress:{tool_name}",
                progress_pct=payload.get("progress"),
            )
            if progress_cb is not None:
                await progress_cb(payload)

        em.publish_progress(exec_ctx, f"tool_start:{tool_name}")
        try:
            text, result = await execute_tool_block(
                block=block,
                session_id=session_id,
                disabled_tools=disabled_tools,
                owner=owner,
                progress_cb=_bridged_progress,
                context=context,
            )
            success = result.get("exit_code", 0) == 0 if isinstance(result, dict) else True
            if success:
                em.publish_completed(exec_ctx, result)
            else:
                em.publish_failed(
                    exec_ctx, result.get("error", "") if isinstance(result, dict) else str(result),
                )
            em.record_trace(
                exec_ctx, f"tool:{tool_name}",
                text[:500] if text else "",
                success,
            )
            return text, result
        except Exception as exc:
            em.publish_failed(exec_ctx, str(exc))
            em.record_trace(
                exec_ctx, f"tool:{tool_name}", str(exc), False,
            )
            return "", {"error": str(exc), "exit_code": 1}


tool_executor = ToolExecutor()
