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
from core.planner import PlannerExecutor
from core.tools._constants import ToolBlock
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
        """Run model with full JARVIS architecture including planner enforcement.

        Phase 3b approach:
          1. LLM proposes tool calls using tool schemas
          2. Planner detects early termination / missing steps
          3. Planner enforces required steps via inject_task (narrow LLM prompt for params)
          4. Loop detection prevents infinite execution
        """
        planner = PlannerExecutor()
        plan = planner.create_plan(task.goal)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task.goal},
        ]

        tool_names: list[str] = []
        hallucinated: list[str] = []
        loop_count = 0
        completed_naturally = False
        turn_count = 0
        early_termination_count = 0
        enforced_steps: list[str] = []
        hallucinated_turn_count = 0
        max_turns_without_progress = 3

        # Track tool sequences for loop detection
        tool_sequence: list[str] = []
        sequence_for_loop = False
        no_tool_count = 0

        # ── Helper: enforce missing steps ────────────────────────────
        async def _enforce_missing_steps(missing: list[str]) -> bool:
            nonlocal hallucinated_turn_count, early_termination_count
            enforced = 0
            for step_name in missing:
                overrides = {}
                if step_name == "email":
                    _, forced_tc = await self.adapter.generate(
                        messages + [{"role": "user", "content": "Provide parameters for send_email. Reply with ONLY a tool call containing to, subject, and body."}],
                        tools=TOOL_SCHEMAS, timeout=task.timeout_seconds,
                    )
                    if forced_tc:
                        fa = forced_tc[0].get("arguments", {})
                        if "to" in fa: overrides["to"] = fa["to"]
                        if "subject" in fa: overrides["subject"] = fa["subject"]
                        if "body" in fa: overrides["body"] = fa["body"]
                elif step_name == "research":
                    _, forced_tc = await self.adapter.generate(
                        messages + [{"role": "user", "content": "Provide the URL for browser_navigate. Reply with ONLY a tool call containing a url parameter."}],
                        tools=TOOL_SCHEMAS, timeout=task.timeout_seconds,
                    )
                    if forced_tc:
                        fa = forced_tc[0].get("arguments", {})
                        if "url" in fa: overrides["url"] = fa["url"]

                result = await planner.inject_task(plan.template_id, step_name, overrides)
                task_info = planner.get_task_for_step(plan.template_id, step_name)
                tool_name = task_info["tool"] if task_info else step_name
                tool_names.append(tool_name)
                tool_sequence.append(tool_name)
                enforced_steps.append(tool_name)
                enforced += 1
                msg_text = str(result.get("result", result))[:500]
                messages.append({"role": "tool", "tool_call_id": tool_name, "content": f"[Planner-enforced] {msg_text}"})

            if enforced:
                early_termination_count += enforced
            hallucinated_turn_count = 0
            return planner.is_workflow_complete(plan.template_id)

        for turn in range(max_turns):
            turn_count += 1

            # Call LLM with tool schemas
            content, tool_calls = await self.adapter.generate(
                messages, tools=TOOL_SCHEMAS, timeout=task.timeout_seconds,
            )

            if content:
                messages.append({"role": "assistant", "content": content})

            # ── Hallucination detection ──────────────────────────────
            all_hallucinated = False
            if tool_calls and plan is not None:
                hallucinated_this_turn = 0
                for tc in tool_calls:
                    name = tc.get("name", "")
                    if name not in VALID_TOOLS:
                        hallucinated_this_turn += 1
                if hallucinated_this_turn == len(tool_calls):
                    all_hallucinated = True

            # ── Planner Enforcement ─────────────────────────────────
            if plan is not None:
                should_enforce = False
                if not tool_calls:
                    no_tool_count += 1
                    if no_tool_count > 1 or tool_names:
                        should_enforce = True
                elif all_hallucinated:
                    hallucinated_turn_count += 1
                    if hallucinated_turn_count >= max_turns_without_progress:
                        should_enforce = True
                else:
                    no_tool_count = 0
                    hallucinated_turn_count = 0

                if should_enforce:
                    if planner.is_workflow_complete(plan.template_id):
                        break
                    missing = planner.check_early_termination(plan.template_id, tool_names)
                    if missing:
                        done = await _enforce_missing_steps(missing)
                        if done:
                            break
                        continue

                    # No missing steps and no tool calls — model is done
                    if no_tool_count >= 2:
                        completed_naturally = True
                        break

                    # Reset counters if model was just taking a break
                    if not tool_calls:
                        messages.append({
                            "role": "user",
                            "content": "Continue working on the task using the available tools.",
                        })
                        continue

            if not tool_calls:
                continue

            if not all_hallucinated:
                no_tool_count = 0
                hallucinated_turn_count = 0

            for tc in tool_calls:
                name = tc.get("name", "")
                tc_args = tc.get("arguments", {})

                # Validate tool name
                if name not in VALID_TOOLS:
                    hallucinated.append(name)
                    continue

                tool_names.append(name)
                tool_sequence.append(name)

                # Record step in planner
                if plan is not None:
                    planner.record_step(plan.template_id, name, True)

                # Execute the tool
                try:
                    import json as _json
                    content_str = tc_args if isinstance(tc_args, str) else _json.dumps(tc_args)
                    block = ToolBlock(tool_type=name, content=content_str)
                    _, result = await execute_tool_block(block, owner="dev")
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

            # Workflow complete — exit early even if LLM keeps generating
            if plan is not None and planner.is_workflow_complete(plan.template_id):
                break

        # Finalize planner
        if plan is not None:
            planner.finalize(plan.template_id, planner.is_workflow_complete(plan.template_id))

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
                "early_termination_count": early_termination_count,
                "enforced_steps": enforced_steps,
                "planner_template": plan.template_id if plan else None,
                "planner_completed": planner.is_workflow_complete(plan.template_id) if plan else None,
            },
        }
