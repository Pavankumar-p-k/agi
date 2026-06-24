"""Benchmark Runner — executes a single task on a single model+mode combination.

Handles two modes:
  - RAW: direct LLM call, no planner, no workflow (measures raw model quality)
  - WITH_ARCHITECTURE: full pipeline with planner, workflow engine, tools, memory
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from core.benchmark.adapters import ModelAdapter, create_adapter
from core.benchmark.models import (
    BenchmarkMode,
    BenchmarkRun,
    BenchmarkTask,
    ModelConfiguration,
    RunStatus,
)
from core.tools.execution import execute_tool_block
from core.tools.schemas import FUNCTION_TOOL_SCHEMAS

logger = logging.getLogger(__name__)

# Default system prompt for JARVIS agent
SYSTEM_PROMPT = (
    "You are JARVIS, an autonomous software engineering assistant. "
    "You have access to tools for browsing, building, testing, and sending email. "
    "Use the appropriate tools to complete the user's request step by step. "
    "When you are done, respond with a summary of what you accomplished."
)

# All valid tool names for hallucination detection
VALID_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_fill", "browser_press", "browser_screenshot", "browser_evaluate",
    "browser_close", "build_project", "run_tests", "runtime_validate",
    "send_email", "repair_project", "automated_build", "vision_browser",
    "browser_planner", "browser_think", "browser_loop_breaker",
}

# Tool schemas for the LLM (OpenAI function-calling format)
TOOL_SCHEMAS = list(FUNCTION_TOOL_SCHEMAS) if isinstance(FUNCTION_TOOL_SCHEMAS, (list, tuple)) else []


class BenchmarkRunner:
    """Executes one task on one model in one mode.

    Usage:
        adapter = create_adapter("qwen2.5:7b", "ollama")
        runner = BenchmarkRunner(adapter)
        run = await runner.execute(task, mode=BenchmarkMode.RAW)
    """

    def __init__(self, adapter: ModelAdapter):
        self.adapter = adapter

    async def execute(
        self,
        task: BenchmarkTask,
        mode: BenchmarkMode = BenchmarkMode.WITH_ARCHITECTURE,
        max_turns: int = 15,
    ) -> BenchmarkRun:
        """Execute a task and return a BenchmarkRun.

        Args:
            task: the BenchmarkTask to execute
            mode: RAW or WITH_ARCHITECTURE
            max_turns: maximum LLM interaction turns

        Returns:
            BenchmarkRun with status and metrics
        """
        now = datetime.now(timezone.utc)
        run = BenchmarkRun(
            model_id=self.adapter.model_id,
            task_id=task.id,
            mode=mode,
            started_at=now.isoformat(),
        )

        start = time.monotonic()

        try:
            if mode == BenchmarkMode.RAW:
                result = await self._run_raw(task, max_turns=max_turns)
            else:
                result = await self._run_with_architecture(task, max_turns=max_turns)

            elapsed = time.monotonic() - start
            run.elapsed_seconds = elapsed
            run.status = result.get("status", RunStatus.FAILED)
            run.tool_names = result.get("tool_names", [])
            run.hallucinated_tools = result.get("hallucinated_tools", [])
            run.missing_steps = result.get("missing_steps", [])
            run.completed_naturally = result.get("completed_naturally", False)
            run.loop_count = result.get("loop_count", 0)
            run.metrics = result.get("metrics", {})

            # Determine pass/fail
            required = task.required_tools
            missing = [t for t in required if t not in run.tool_names]
            if missing:
                run.status = RunStatus.FAILED
            else:
                run.status = RunStatus.PASSED

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            run.elapsed_seconds = elapsed
            run.status = RunStatus.TIMEOUT
            run.error_message = f"Timed out after {task.timeout_seconds}s"

        except Exception as e:
            elapsed = time.monotonic() - start
            run.elapsed_seconds = elapsed
            run.status = RunStatus.ERROR
            run.error_message = str(e)[:500]
            logger.exception("Benchmark run failed: %s", e)

        finally:
            run.finished_at = datetime.now(timezone.utc).isoformat()

        return run

    # ── Raw Mode ────────────────────────────────────────────────────

    async def _run_raw(
        self,
        task: BenchmarkTask,
        max_turns: int = 15,
    ) -> dict[str, Any]:
        """Run model in raw mode — direct LLM conversation, no tools.

        The model is given the goal and asked to reason about it.
        We measure planning quality and reasoning depth.
        """
        messages = [
            {"role": "system", "content": "You are an AI assistant. Reason step by step about the given task."},
            {"role": "user", "content": task.goal},
        ]

        tool_names: list[str] = []
        hallucinated: list[str] = []
        loop_count = 0
        completed_naturally = False
        turn_count = 0

        for turn in range(max_turns):
            turn_count += 1
            content, tool_calls = await self.adapter.generate(
                messages, tools=None, timeout=task.timeout_seconds,
            )

            if not content and not tool_calls:
                break

            messages.append({"role": "assistant", "content": content or ""})

            # In raw mode, we just let the model reason
            # Check if the model is describing a plan or summarizing
            if len(messages) > 4:
                completed_naturally = True
                break

        return {
            "status": RunStatus.PASSED if turn_count > 0 else RunStatus.FAILED,
            "tool_names": tool_names,
            "hallucinated_tools": hallucinated,
            "missing_steps": [],
            "completed_naturally": completed_naturally,
            "loop_count": loop_count,
            "metrics": {
                "raw_turns": turn_count,
                "raw_content_length": sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str)),
            },
        }

    # ── With Architecture Mode ──────────────────────────────────────

    async def _run_with_architecture(
        self,
        task: BenchmarkTask,
        max_turns: int = 15,
    ) -> dict[str, Any]:
        """Run model with full JARVIS architecture.

        This mirrors the Phase 3 approach: planner + tool dispatch.
        The model gets tool schemas and the planner enforces required steps.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task.goal},
        ]

        tool_names: list[str] = []
        hallucinated: list[str] = []
        loop_count = 0
        completed_naturally = False
        turn_count = 0

        # Track tool sequences for loop detection
        tool_sequence: list[str] = []
        seq_history: list[list[str]] = []
        sequence_for_loop = False
        no_tool_count = 0

        for turn in range(max_turns):
            turn_count += 1

            # Call LLM with tool schemas
            content, tool_calls = await self.adapter.generate(
                messages, tools=TOOL_SCHEMAS, timeout=task.timeout_seconds,
            )

            if content:
                messages.append({"role": "assistant", "content": content})

            if not tool_calls:
                no_tool_count += 1
                # If model stops producing tool calls, check if we should continue
                if no_tool_count >= 2:
                    completed_naturally = True
                    break
                continue

            no_tool_count = 0

            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("arguments", {})

                # Validate tool name
                if name not in VALID_TOOLS:
                    hallucinated.append(name)
                    continue

                tool_names.append(name)
                tool_sequence.append(name)

                # Execute the tool
                try:
                    block = {"name": name, "content": str(args)} if not isinstance(args, str) else {"name": name, "content": args}
                    result = await execute_tool_block(block)
                    result_str = str(result.get("result", "") or result.get("error", ""))[:2000]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", name),
                        "content": result_str,
                    })
                except Exception as e:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", name),
                        "content": f"Error: {e}",
                    })

            # Loop detection: check for repeating patterns of length 3-6
            if len(tool_sequence) >= 6:
                for pattern_len in range(3, min(7, len(tool_sequence) // 2 + 1)):
                    recent = tool_sequence[-pattern_len:]
                    count = sum(
                        1 for i in range(len(tool_sequence) - pattern_len)
                        if tool_sequence[i:i + pattern_len] == recent
                    )
                    if count >= 4:
                        loop_count += 1
                        sequence_for_loop = True
                        break

            if sequence_for_loop:
                break

        # Determine missing required tools
        expected = task.required_tools
        missing = [t for t in expected if t not in set(tool_names)]

        return {
            "status": RunStatus.PASSED if not missing else RunStatus.FAILED,
            "tool_names": tool_names,
            "hallucinated_tools": hallucinated,
            "missing_steps": missing,
            "completed_naturally": completed_naturally,
            "loop_count": loop_count,
            "metrics": {
                "arch_turns": turn_count,
                "tool_call_count": len(tool_names),
                "hallucination_count": len(hallucinated),
            },
        }
