"""AgentDrivenExecutor — decompose → route → execute → enforce.

Bridges the planner state machine to the agent system: a goal is
decomposed into SubGoals, routed to agents, executed, and missing
required steps are enforced (re-injected) before returning.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

# Module-level imports so tests can patch core.agents.executor.get_agent /
# core.agents.executor.execute_tool_block
from core.agents.router import get_agent
from core.tools.execution import execute_tool_block

ExecuteFn = Callable[[str, Any], Awaitable[dict[str, Any]]]

# Templates: goal keyword -> ordered required step names.
_TEMPLATES: dict[str, list[str]] = {
    "android": ["research", "build", "test", "email"],
    "app": ["research", "build", "test", "email"],
    "apk": ["build", "test", "email"],
    "report": ["research", "build", "email"],
}

_STEP_AGENT_HINTS: dict[str, str] = {
    "research": "research",
    "build": "build",
    "test": "test",
    "email": "email",
}


def _select_template(goal: str) -> list[str]:
    text = (goal or "").lower()
    for keyword, steps in _TEMPLATES.items():
        if keyword in text:
            return list(steps)
    return []


async def _execute_step(step: str, goal: str, ctx_vars: dict[str, Any]) -> dict[str, Any]:
    """Route one step to its agent; fall back to the tool executor."""
    agent_id = _STEP_AGENT_HINTS.get(step, "")
    agent = get_agent(agent_id) if agent_id else None
    if agent is not None:
        ec = _make_execution_context(goal, ctx_vars)
        # ExecutionContext as first positional arg: BaseAgent.execute treats a
        # non-str first argument as the context and reads goal from it.
        result = await agent.execute(ec)
        if isinstance(result, dict):
            # Tool-style dict result from mocked/custom agents
            return {
                "output": str(result.get("output", "")),
                "exit_code": int(result.get("exit_code", 0 if result.get("success", True) else 1)),
                "error": str(result.get("error", "") or ""),
                "_artifacts": dict(result.get("_artifacts") or result.get("artifacts") or {}),
            }
        d = result.to_dict()
        return {"output": d.get("output", ""), "exit_code": 0 if d.get("success") else 1,
                "error": d.get("error", ""), "_artifacts": dict(d.get("artifacts") or {})}

    # Fallback: execute_tool_block (tool layer)
    tool_name, result = await execute_tool_block({"tool": step, "params": {"goal": goal}})
    return result if isinstance(result, dict) else {"output": str(result), "exit_code": 0}


def _make_execution_context(goal: str, variables: dict[str, Any]):
    from core.types import ExecutionContext
    return ExecutionContext(goal=goal, variables=dict(variables or {}))


def make_agent_execute_fn(global_context: dict[str, Any] | None = None) -> ExecuteFn:
    """Build the PlannerStateMachine execute_fn.

    Returns async fn(goal, executor) -> {
        artifacts, tool_calls, tool_names, error?
    }
    """
    ctx_vars = dict(global_context or {})

    async def execute_fn(goal: str, executor: Any) -> dict[str, Any]:
        from core.planner.decomposer import GoalDecomposer
        from core.planner.models import SubGoal

        result: dict[str, Any] = {
            "artifacts": {}, "tool_calls": [], "tool_names": [], "error": "",
        }
        if not goal or not str(goal).strip():
            return result

        # 1) Decompose
        try:
            tree = GoalDecomposer().decompose(str(goal))
            subgoals = tree.flatten() if tree else []
        except Exception:  # noqa: BLE001 — decomposition is best-effort
            subgoals = []

        # 2) Route + 3) Execute each sub-goal
        executed_steps: list[str] = []
        for sg in subgoals:
            step = getattr(sg, "step_name", "") or ""
            desc = getattr(sg, "description", "") or str(goal)
            if not step:
                continue
            outcome = await _execute_step(step, desc, ctx_vars)
            executed_steps.append(step)
            result["tool_calls"].append(f"{step}: {str(outcome.get('output', ''))[:120]}")
            result["tool_names"].append(step)
            arts = outcome.get("_artifacts") or {}
            if isinstance(arts, dict):
                result["artifacts"].update(arts)
            if outcome.get("error"):
                result["error"] = f"{step}: {outcome['error']}"

        # 4) Enforce missing required steps from the matched template
        template = _select_template(str(goal))
        missing = [s for s in template if s not in executed_steps]
        for step in missing:
            desc = f"enforced: {step} for {goal}"
            outcome = await _execute_step(step, desc, ctx_vars)
            executed_steps.append(step)
            result["tool_calls"].append(f"enforced:{step}")
            result["tool_names"].append(step)
            arts = outcome.get("_artifacts") or {}
            if isinstance(arts, dict):
                result["artifacts"].update(arts)

        return result

    return execute_fn


__all__ = ["make_agent_execute_fn", "ExecuteFn"]
