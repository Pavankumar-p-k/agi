"""AgentDrivenExecutor — bridges GoalDecomposer + AgentRouter + PlannerExecutor.

Provides execute_fn callables compatible with PlannerStateMachine.run().

Two modes:
  - make_agent_execute_fn()    — sequential execution (existing)
  - make_parallel_agent_execute_fn() — phase-parallel execution (new)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from core.agents.graph import GraphNode, NodeStatus, build_graph_from_tasks
from core.agents.parallel_executor import ParallelAgentExecutor
from core.agents.router import AgentRouter, find_agent_for_goal, get_agent
from core.planner.executor import PlannerExecutor
from core.planner.templates import STEP_TO_PRIMARY_TOOL, TOOL_TO_STEP
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block
from core.workflow.context import ExecutionContext

logger = logging.getLogger(__name__)


def make_agent_execute_fn(
    router: AgentRouter | None = None,
    global_context: dict[str, Any] | None = None,
) -> Callable[[str, PlannerExecutor], Awaitable[dict[str, Any]]]:
    """Return an execute_fn compatible with PlannerStateMachine.run().

    The returned function:
    1. Creates an execution plan for step tracking
    2. Decomposes the goal into sub-goals via GoalDecomposer
    3. Routes sub-goals to capable agents via AgentRouter
    4. Executes each agent task sequentially
    5. Enforces any missing required steps via inject_task

    Usage:
        planner = PlannerExecutor()
        sm = PlannerStateMachine(planner)
        execute_fn = make_agent_execute_fn()
        result = await sm.run(goal, execute_fn)
    """
    _router = router or AgentRouter()
    _ctx = dict(global_context or {})
    _counter: list[int] = [0]

    async def _agent_enforce(tool_name: str, default_args: dict) -> dict:
        """Execute_fn for inject_task — maps tool_name to agent and executes."""
        step_name = TOOL_TO_STEP.get(tool_name, tool_name)
        agent = get_agent(step_name)

        if not agent:
            agent = find_agent_for_goal(step_name)

        if not agent:
            # Fallback: execute the tool directly
            block = ToolBlock(
                tool_type=tool_name,
                content=json.dumps(default_args),
            )
            _, result = await execute_tool_block(block)
            return result

        _counter[0] += 1
        ec = ExecutionContext(
            workflow_id=f"enforce_{step_name}_{_counter[0]}",
            owner="planner",
            session_id="",
            variables=dict(default_args),
        )
        if _ctx:
            ec.variables.update(_ctx)

        return await agent.execute(ec)

    async def execute_fn(goal: str, executor: PlannerExecutor) -> dict[str, Any]:
        """Agent-driven execution: decompose → route → execute → enforce."""
        plan = executor.create_plan(goal)
        plan_id = plan.template_id if plan else None

        tree = executor.decompose_goal(goal)
        tasks = _router.route(tree, context=_ctx)

        all_artifacts: dict[str, Any] = {}
        tool_calls: list[str] = []
        tool_names: list[str] = []
        errors: list[str] = []

        # Execute each agent task
        for task in tasks:
            agent = get_agent(task["agent_id"])
            if not agent:
                logger.warning(
                    "AgentDrivenExecutor: no agent for task %s", task["agent_id"]
                )
                continue

            _counter[0] += 1
            ec = ExecutionContext(
                workflow_id=f"agent_{task['agent_id']}_{_counter[0]}",
                owner="planner",
                session_id="",
                variables=dict(task.get("parameters", {})),
            )
            if _ctx:
                for k, v in _ctx.items():
                    if k not in ec.variables:
                        ec.variables[k] = v

            result = await agent.execute(ec)

            step_ok = (
                result.get("exit_code", -1) == 0
                or result.get("sent") is True
                or result.get("success", False) is True
                or (
                    result.get("error") is None
                    and result.get("output") is not None
                )
            )

            if plan_id:
                executor.record_step(plan_id, task["agent_id"], step_ok)

            task_artifacts = result.get("_artifacts", {})
            if task_artifacts:
                all_artifacts.update(task_artifacts)

            step_name = task.get("step", task["agent_id"])
            tool_calls.append(step_name)
            tool_names.append(step_name)

            if not step_ok:
                err_msg = result.get("error") or f"{task['agent_id']} failed"
                errors.append(err_msg)

            logger.info(
                "AgentDrivenExecutor: %s -> ok=%s artifacts=%s",
                task["agent_id"], step_ok, list(task_artifacts.keys()),
            )

        # Enforce missing required steps
        if plan_id:
            missing = executor.check_early_termination(plan_id, tool_names)
            if missing:
                logger.info(
                    "AgentDrivenExecutor: enforcing missing steps: %s", missing
                )
                for step_name in missing:
                    task_info = executor.get_task_for_step(plan_id, step_name)
                    if task_info:
                        result = await _agent_enforce(task_info["tool"], task_info.get("default_args", {}))
                        executor.record_step(plan_id, step_name, result.get("exit_code", -1) == 0 or result.get("sent") is True)
                    else:
                        result = {"exit_code": 1, "error": f"Unknown step: {step_name}"}
                    enforced_artifacts = result.get("_artifacts", {})
                    if enforced_artifacts:
                        all_artifacts.update(enforced_artifacts)
                    tool_calls.append(f"enforced:{step_name}")
                    tool_names.append(step_name)

                    step_ok = (
                        result.get("exit_code", -1) == 0
                        or result.get("sent") is True
                    )
                    if not step_ok:
                        err_msg = result.get("error") or f"enforced:{step_name} failed"
                        errors.append(err_msg)

        return {
            "artifacts": all_artifacts,
            "tool_calls": tool_calls,
            "tool_names": tool_names,
            "error": "; ".join(errors) if errors else None,
            "planner_metrics": executor.metrics,
            "completed_naturally": True,
        }

    return execute_fn


# ── Parallel Execution ─────────────────────────────────────────────────────

def make_parallel_agent_execute_fn(
    router: AgentRouter | None = None,
    global_context: dict[str, Any] | None = None,
    max_parallel: int = 5,
) -> Callable[[str, PlannerExecutor], Awaitable[dict[str, Any]]]:
    """Return an execute_fn that runs agent tasks with phase-parallel execution.

    Same contract as make_agent_execute_fn() but:
    - Tasks within the same phase (step_name) run concurrently
    - Phases are sequential barriers (all research → all build → all test → ...)
    - Enforces missing required steps after graph execution
    """
    _router = router or AgentRouter()
    _ctx = dict(global_context or {})
    _counter: list[int] = [0]

    async def _agent_enforce(tool_name: str, default_args: dict) -> dict:
        """Execute_fn for inject_task — maps tool_name to agent and executes."""
        step_name = TOOL_TO_STEP.get(tool_name, tool_name)
        agent = get_agent(step_name)
        if not agent:
            agent = find_agent_for_goal(step_name)
        if not agent:
            block = ToolBlock(
                tool_type=tool_name,
                content=json.dumps(default_args),
            )
            _, result = await execute_tool_block(block)
            return result
        _counter[0] += 1
        ec = ExecutionContext(
            workflow_id=f"enforce_{step_name}_{_counter[0]}",
            owner="planner", session_id="",
            variables=dict(default_args),
        )
        if _ctx:
            ec.variables.update(_ctx)
        return await agent.execute(ec)

    async def execute_fn(goal: str, executor: PlannerExecutor) -> dict[str, Any]:
        plan = executor.create_plan(goal)
        plan_id = plan.template_id if plan else None

        tree = executor.decompose_goal(goal)
        tasks = _router.route(tree, context=_ctx)

        # Build execution graph with phase-parallel layout
        graph = build_graph_from_tasks(tasks)
        graph.max_parallel = max_parallel

        # Execute graph in parallel phases
        parallel_exec = ParallelAgentExecutor(
            max_parallel=max_parallel, emit_events=False,
        )
        graph_result = await parallel_exec.execute(
            graph, workflow_id=f"parallel_{plan_id}" if plan_id else "parallel_graph",
            global_context=_ctx,
        )

        all_artifacts = graph_result.get("artifacts", {})
        errors = graph_result.get("error")

        # Build tool_names for enforcement detection
        tool_names: list[str] = []
        for node in graph.nodes.values():
            step_name = node.agent_id
            if node.status == NodeStatus.COMPLETED:
                tool_names.append(step_name)
                if plan_id:
                    executor.record_step(plan_id, step_name, True)
            elif node.status == NodeStatus.FAILED:
                if plan_id:
                    executor.record_step(plan_id, step_name, False)

        # Enforce missing required steps
        if plan_id:
            missing = executor.check_early_termination(plan_id, tool_names)
            if missing:
                logger.info(
                    "ParallelExecutor: enforcing missing steps: %s", missing
                )
                for step_name in missing:
                    result = await executor.inject_task(
                        plan_id, step_name, overrides=None, context=None,
                    )
                    enforced_artifacts = result.get("_artifacts", {})
                    if enforced_artifacts:
                        all_artifacts.update(enforced_artifacts)
                    tool_names.append(step_name)
                    step_ok = (
                        result.get("exit_code", -1) == 0
                        or result.get("sent") is True
                    )
                    if step_ok and plan_id:
                        executor.record_step(plan_id, step_name, True)

        return {
            "artifacts": all_artifacts,
            "tool_calls": tool_names,
            "tool_names": tool_names,
            "error": errors,
            "planner_metrics": executor.metrics,
            "completed_naturally": True,
        }

    return execute_fn
