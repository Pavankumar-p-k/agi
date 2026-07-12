"""PlannerStateMachine — PLAN → DECOMPOSE → (ROUTE) → EXECUTE → VERIFY → COMPLETE.

Two execution modes:
  - Native agent execution (router provided): decomposes goal, routes each leaf
    to the best-matching agent via AgentRouter, executes through agent.execute().
  - Callback execution (execute_fn provided): backward-compatible path where
    the caller provides an execute_fn that handles decomposition + routing.

Verification is artifact-driven: checks ExecutionContext's artifact store
for expected outputs after each execution cycle.
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Awaitable, Callable

from core.planner.executor import PlannerExecutor
from core.planner.models import SubGoal

logger = logging.getLogger(__name__)


class State(enum.Enum):
    PLAN = "PLAN"
    DECOMPOSE = "DECOMPOSE"
    ROUTE = "ROUTE"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


_VERIFICATION_RULES: dict[str, list[dict[str, Any]]] = {
    "research_build_validate_email": [
        {"key": "email_sent",   "label": "email confirmation"},
        {"key": "snapshot",     "label": "browser snapshot",   "optional": True},
    ],
    "android_app_build": [
        {"key": "email_sent",   "label": "email confirmation"},
    ],
    "research_build_email": [
        {"key": "email_sent",   "label": "email confirmation"},
    ],
    "build_validate_notify": [
        {"key": "email_sent",   "label": "email confirmation",  "optional": True},
    ],
    "step_email": [
        {"key": "email_sent",   "label": "email confirmation"},
    ],
    "step_build": [
        {"key": None,           "label": "build output",       "check": "exit_code"},
    ],
}

_MAX_VERIFY_RETRIES = 2


class PlannerStateMachine:
    """Deterministic state machine that owns the full workflow lifecycle.

    Transitions:
      PLAN → DECOMPOSE → (ROUTE) → EXECUTE → VERIFY → (COMPLETE | EXECUTE)
                                                  → FAILED (after max retries)

    Mode 1 — Native agent routing (recommended):
        sm = PlannerStateMachine(executor, router=AgentRouter())
        await sm.run("Research competitors and implement payment API")

    Mode 2 — Callback-based (legacy benchmarks):
        sm = PlannerStateMachine(executor)
        await sm.run(goal, execute_fn=my_fn)
    """

    def __init__(self, executor: PlannerExecutor, router: Any = None,
                 activity_recorder: Any = None, health_engine: Any = None,
                 replan_engine: Any = None):
        self.executor = executor
        self.router = router
        self.activity_recorder = activity_recorder
        self.health_engine = health_engine
        self.replan_engine = replan_engine
        self.state = State.PLAN
        self.plan: SubGoal | None = None
        self.verification_results: list[dict[str, Any]] = []
        self._verify_retries = 0
        self.context: Any = None

    @property
    def metrics(self) -> dict[str, Any]:
        m = dict(self.executor.metrics)
        m["state_machine_state"] = self.state.value
        m["verify_retries"] = self._verify_retries
        m["verification_passed"] = (
            all(r.get("passed", False) for r in self.verification_results)
        ) if self.verification_results else None
        return m

    def get_verification_rules(self, template_id: str | None) -> list[dict[str, Any]]:
        if template_id and template_id in _VERIFICATION_RULES:
            return _VERIFICATION_RULES[template_id]
        if template_id:
            step_key = f"step_{template_id.replace('step_', '')}"
            if step_key in _VERIFICATION_RULES:
                return _VERIFICATION_RULES[step_key]
        return []

    async def run(
        self,
        goal: str,
        execute_fn: Callable[[str, PlannerExecutor], Awaitable[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        self.state = State.PLAN
        self.verification_results = []
        self._verify_retries = 0
        self._last_execution_result: dict[str, Any] = {}
        _start = time.monotonic()

        result = {
            "goal": goal,
            "state": self.state.value,
            "artifacts": {},
            "verification": [],
            "tool_calls": [],
            "tool_names": [],
            "agent_assignments": [],
            "error": None,
        }

        # ── PLAN ────────────────────────────────────────────────────────
        logger.info("StateMachine: PLAN goal=%r", goal[:60])
        template_id = self.executor.get_plan_id(goal)

        if not template_id:
            result["state"] = State.FAILED.value
            result["error"] = f"No template matched for goal: {goal[:80]}"
            self.state = State.FAILED
            return result

        recorder = self.activity_recorder
        if recorder:
            recorder.record_goal(goal, template_id)

        self.state = State.DECOMPOSE

        # ── DECOMPOSE ───────────────────────────────────────────────────
        logger.info("StateMachine: DECOMPOSE template=%s", template_id)
        tree = self.executor.decompose_goal(goal)
        self.plan = tree
        if recorder:
            recorder.record_subgoals(tree)

        # ── ROUTE (if router available) ─────────────────────────────────
        if self.router:
            self.state = State.ROUTE
            logger.info("StateMachine: ROUTE %d leaves", len(tree.flatten()))
            assignments = self._route_leaves(tree)
            result["agent_assignments"] = assignments

        self.state = State.EXECUTE

        # ── EXECUTE + VERIFY + HEALTH loop ────────────────────────────
        execution_result: dict[str, Any] = {}
        _replan_attempted = False
        while self.state == State.EXECUTE:
            logger.info("StateMachine: EXECUTE (retry=%d)", self._verify_retries)

            if self.router:
                execution_result = await self._execute_agents()
            elif execute_fn:
                execution_result = await self._execute(goal, execute_fn)
            else:
                execution_result = {"artifacts": {}, "error": None}

            self._last_execution_result = execution_result

            if execution_result.get("error"):
                # Check health before declaring FAILED
                if not _replan_attempted and self.health_engine:
                    health = self.health_engine.evaluate(template_id or goal)
                    if health.get("status") in ("replan_recommended", "replan_required"):
                        logger.info("StateMachine: health=%s -> attempting replan", health["status"])
                        if self.replan_engine:
                            replan_opts = self.replan_engine.get_options(template_id or goal)
                            if replan_opts and "error" not in replan_opts:
                                _replan_attempted = True
                                self._verify_retries = 0
                                continue
                result["error"] = execution_result["error"]
                self.state = State.FAILED
                break

            self.state = State.VERIFY

            # ── VERIFY ──────────────────────────────────────────────────
            logger.info("StateMachine: VERIFY template=%s", template_id)
            rules = self.get_verification_rules(template_id)
            artifacts = execution_result.get("artifacts", {})
            passed, details = self._verify(rules, artifacts)

            self.verification_results = details
            result["verification"] = details

            if passed:
                self.state = State.COMPLETE
            else:
                self._verify_retries += 1
                if self._verify_retries >= _MAX_VERIFY_RETRIES:
                    health_replanned = False
                    if not _replan_attempted and self.health_engine:
                        health = self.health_engine.evaluate(template_id or goal)
                        if health.get("status") in ("replan_recommended", "replan_required"):
                            logger.info("StateMachine: health=%s after verify fail -> replan", health["status"])
                            if self.replan_engine:
                                replan_opts = self.replan_engine.get_options(template_id or goal)
                                if replan_opts and "error" not in replan_opts:
                                    _replan_attempted = True
                                    health_replanned = True
                                    self._verify_retries = 0
                                    self.state = State.EXECUTE
                    if not health_replanned:
                        logger.warning("StateMachine: verification failed after %d retries", _MAX_VERIFY_RETRIES)
                        self.state = State.FAILED
                        result["error"] = "Verification failed after max retries"
                else:
                    logger.info("StateMachine: verification failed -> re-EXECUTE")
                    self.state = State.EXECUTE

        # ── COMPLETE / FAILED ───────────────────────────────────────────
        result["state"] = self.state.value
        result["artifacts"] = execution_result.get("artifacts", {})
        result["tool_calls"] = execution_result.get("tool_calls", [])
        result["tool_names"] = execution_result.get("tool_names", [])
        result["planner_metrics"] = execution_result.get("planner_metrics", {})
        result["hallucinated_tools"] = execution_result.get("hallucinated_tools", [])
        result["loop_count"] = execution_result.get("loop_count", 0)
        result["completed_naturally"] = execution_result.get("completed_naturally", False)
        result["elapsed"] = time.monotonic() - _start
        result["metrics"] = self.metrics
        if recorder:
            if self.state == State.COMPLETE:
                recorder.record_completion(result)
            elif self.state == State.FAILED:
                recorder.record_failure(result.get("error", "Unknown failure"))
        logger.info("StateMachine: final state=%s artifacts=%s elapsed=%.1fs",
                     self.state.value, list(result["artifacts"].keys()), result["elapsed"])
        return result

    def _route_leaves(self, root: SubGoal) -> list[dict[str, Any]]:
        """Assign agent_id to each leaf subgoal via AgentRouter.

        Returns list of assignment dicts for result reporting.
        """
        from core.agents.router import find_best_agent_for_subgoal

        leaves = root.flatten()
        assignments: list[dict[str, Any]] = []

        for leaf in leaves:
            agent = find_best_agent_for_subgoal(leaf)
            if agent:
                leaf.agent_id = agent.agent_id
                assignments.append({
                    "subgoal_id": leaf.id,
                    "description": leaf.description[:60],
                    "agent_id": agent.agent_id,
                    "step_name": leaf.step_name,
                })
                logger.debug("Route: %s -> %s (step=%s)", leaf.id, agent.agent_id, leaf.step_name)
            else:
                logger.warning("Route: no agent for leaf %s (%s)", leaf.id, leaf.description[:60])

        return assignments

    async def _execute_agents(self) -> dict[str, Any]:
        """Execute routed leaf subgoals using the parallel agent graph.

        Builds a dependency graph from leaf subgoals where later-phase nodes
        depend on earlier-phase nodes, enabling artifact handoff between agents.
        Falls back to sequential execution for backward compatibility (no router).
        """
        from core.agents.graph import NodeStatus, get_phase_for_step
        from core.agents.parallel_executor import ParallelAgentExecutor
        from core.agents.router import get_agent
        from core.workflow.context import ExecutionContext

        if not self.plan:
            return {"artifacts": {}, "error": "No plan"}

        tree = self.plan
        leaves = tree.flatten()

        leaves_with_agents = [l for l in leaves if l.agent_id]
        if not leaves_with_agents:
            return {"artifacts": {}, "error": None, "tool_names": []}

        # Build task list from leaf subgoals
        tasks: list[dict] = []
        for leaf in leaves_with_agents:
            agent = get_agent(leaf.agent_id)
            if not agent:
                logger.warning("Execute: agent %s not found for leaf %s", leaf.agent_id, leaf.id)
                continue
            tasks.append({
                "agent_id": leaf.agent_id,
                "goal": leaf.description,
                "step": leaf.step_name or leaf.agent_id,
                "parameters": dict(leaf.parameters),
            })

        if not tasks:
            return {"artifacts": {}, "error": None, "tool_names": []}

        # Record agent tasks (before execution)
        recorder = self.activity_recorder
        if recorder:
            recorder.record_agent_tasks(tasks)

        # Build dependency edges based on step phase ordering
        # Later phases depend on all earlier phases for artifact handoff
        edges: list[tuple[str, str, dict[str, str]]] = []
        for i in range(len(tasks)):
            phase_i = get_phase_for_step(tasks[i].get("step", tasks[i]["agent_id"]))
            for j in range(len(tasks)):
                if i == j:
                    continue
                phase_j = get_phase_for_step(tasks[j].get("step", tasks[j]["agent_id"]))
                if phase_i < phase_j:
                    # task_j depends on task_i — pass task_i's agent_id as parameter key
                    edges.append((
                        f"n_{i}", f"n_{j}",
                        {f"{tasks[i]['agent_id']}_output": f"{tasks[i]['agent_id']}_data"},
                    ))

        # Build and execute the graph
        from core.agents.graph import build_graph_from_tasks
        graph = build_graph_from_tasks(tasks, edges=edges)
        graph.max_parallel = min(len(tasks), 5)

        parallel_exec = ParallelAgentExecutor(max_parallel=graph.max_parallel, emit_events=False)
        graph_result = await parallel_exec.execute(graph, workflow_id="agent_exec")

        all_artifacts = graph_result.get("artifacts", {})
        errors = graph_result.get("error")

        # Record agent task results
        if recorder:
            for task in tasks:
                task_key = f"{task['agent_id']}:{task['goal']}::{task.get('step', task['agent_id'])}"
                task_artifacts = all_artifacts.get(task["agent_id"], {})
                if task_artifacts:
                    recorder.record_task_artifacts(task, task_artifacts)
                if errors:
                    recorder.record_task_result(task, success=False, error=str(errors))
                else:
                    recorder.record_task_result(task, success=True,
                                                 output={"artifacts": task_artifacts})

        tool_names: list[str] = []
        for node in graph.nodes.values():
            step_name = node.agent_id
            if node.status == NodeStatus.COMPLETED:
                tool_names.append(step_name)

        return {
            "artifacts": all_artifacts,
            "tool_calls": tool_names,
            "tool_names": tool_names,
            "error": errors,
            "planner_metrics": self.executor.metrics,
            "completed_naturally": True,
        }

    async def _execute(
        self,
        goal: str,
        execute_fn: Callable[[str, PlannerExecutor], Awaitable[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """Legacy execution path via caller-provided callback."""
        if execute_fn:
            return await execute_fn(goal, self.executor)
        return {"artifacts": {}, "error": None}

    def _verify(
        self,
        rules: list[dict[str, Any]],
        artifacts: dict[str, Any],
    ) -> tuple[bool, list[dict[str, Any]]]:
        if not rules:
            return True, []

        details = []
        all_passed = True

        for rule in rules:
            key = rule.get("key")
            label = rule.get("label", key or "unknown")
            optional = rule.get("optional", False)

            if key is None:
                result = {"rule": label, "passed": True, "check": "skipped"}
            elif key in artifacts:
                result = {"rule": label, "passed": True, "artifact_id": artifacts[key]}
            elif optional:
                result = {"rule": label, "passed": True, "note": "optional, not found"}
            else:
                result = {"rule": label, "passed": False, "note": "missing artifact"}
                all_passed = False

            details.append(result)

        return all_passed, details

    def is_verification_passed(self) -> bool | None:
        if not self.verification_results:
            return None
        return all(r.get("passed", False) for r in self.verification_results)
