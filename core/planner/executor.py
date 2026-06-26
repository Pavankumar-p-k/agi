"""PlannerExecutor — loads templates, creates execution plans, tracks progress, verifies completion, enforces steps."""

import logging
import os
from typing import Any, Awaitable, Callable

from core.planner.classifier import classify, extract_parameters
from core.planner.decomposer import GoalDecomposer
from core.planner.models import ExecutionPlan, SubGoal
from core.planner.templates import (
    STEP_TO_PRIMARY_TOOL,
    get_template,
    match_required_tools,
    normalize_tool_names,
)

logger = logging.getLogger(__name__)

# Default argument templates for each step.
# Used when LLM parameter generation fails or is unavailable.
# Set JARVIS_TEST_EMAIL env var to override the test recipient.
_JARVIS_TEST_EMAIL = os.environ.get("JARVIS_TEST_EMAIL", "autobot99123@gmail.com")

STEP_DEFAULT_ARGS: dict[str, dict] = {
    "research": {"url": "https://www.google.com"},
    "build":    {},
    "test":     {},
    "validate": {},
    "email":    {
        "to": _JARVIS_TEST_EMAIL,
        "subject": "Workflow Complete",
        "body": "The automated workflow has completed all required steps.",
    },
    "apk":      {},
    "notify":   {
        "to": _JARVIS_TEST_EMAIL,
        "subject": "Build Notification",
        "body": "The build workflow has completed.",
    },
}


class PlannerExecutor:
    """Deterministic planner that converts goals into tracked execution plans.

    Responsibilities:
    - Classify goal → template
    - Create execution plan from template
    - Track completed / pending / failed steps
    - Detect early termination
    - Enforce completion criteria by injecting required tool executions
    """

    def __init__(self):
        self._plans: dict[str, ExecutionPlan] = {}
        self._decomposer = GoalDecomposer()
        self._metrics: dict[str, int] = {
            "planner_templates_used": 0,
            "missing_steps_detected": 0,
            "early_termination_prevented": 0,
            "workflow_completion_rate": 0,
            "total_workflows": 0,
            "completed_workflows": 0,
        }

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def create_plan(self, goal: str) -> ExecutionPlan | None:
        """Classify a goal and create an execution plan. Returns None if no template matches."""
        template_id = classify(goal)
        if not template_id:
            logger.info("Planner: no template matched for goal=%r", goal[:60])
            return None

        template = get_template(template_id)
        if not template:
            return None

        parameters = extract_parameters(goal, template_id)

        # Build step list from template
        steps: list[dict[str, Any]] = []
        for step_name in template.required_steps:
            steps.append({"name": step_name, "required": True})
        for step_name in template.optional_steps:
            steps.append({"name": step_name, "required": False})

        plan = ExecutionPlan(
            template_id=template_id,
            parameters=parameters,
            steps=steps,
            pending_steps=[s["name"] for s in steps],
        )

        # Store plan keyed by template_id for easy lookup
        self._plans[template_id] = plan
        self._metrics["planner_templates_used"] += 1
        self._metrics["total_workflows"] += 1

        logger.info("Planner: created plan=%s steps=%d params=%s",
                     template_id, len(steps), parameters)
        return plan

    def decompose_goal(self, goal: str) -> SubGoal:
        """Decompose a complex goal into hierarchical sub-goals.

        Returns a SubGoal tree. Leaf nodes map to templates or tool steps.
        """
        tree = self._decomposer.decompose(goal)
        self._metrics["goals_decomposed"] = self._metrics.get("goals_decomposed", 0) + 1
        self._metrics["subgoals_created"] = (
            self._metrics.get("subgoals_created", 0) + len(tree.flatten())
        )
        return tree

    def create_decomposed_plan(self, goal: str) -> SubGoal | None:
        """Decompose a goal and create execution plans for each leaf sub-goal.

        Each leaf sub-goal with a template_id becomes an ExecutionPlan managed
        by this executor. Returns the root SubGoal tree for inspection.
        """
        tree = self.decompose_goal(goal)
        leaves = tree.flatten()

        for leaf in leaves:
            if leaf.template_id:
                # Create a plan for template-based sub-goals
                plan = self.create_plan(leaf.description)
                if plan:
                    leaf.parameters = plan.parameters
            elif leaf.step_name and leaf.step_name not in self._plans:
                # Register step-name leafs as pseudo-plans for tracking
                tool = STEP_TO_PRIMARY_TOOL.get(leaf.step_name, leaf.step_name)
                pseudo = ExecutionPlan(
                    template_id=f"step_{leaf.step_name}",
                    parameters=leaf.parameters,
                    steps=[{"name": leaf.step_name, "required": True}],
                    pending_steps=[leaf.step_name],
                )
                self._plans[pseudo.template_id] = pseudo

        logger.info("Planner: decomposed goal -> %d leaves, %d plans",
                     len(leaves), len([l for l in leaves if l.template_id]))
        return tree

    def record_step(self, plan_id: str, tool_name: str, success: bool) -> None:
        """Record a completed or failed step in the plan.

        The tool_name (e.g. build_project) is normalized to its abstract step
        name (e.g. build) before storage. A single tool may satisfy multiple
        step types via TOOL_STEP_ALIASES — all matching steps are recorded.
        """
        plan = self._plans.get(plan_id)
        if not plan:
            return

        # Normalize concrete tool name to abstract step names (may be >1
        # if TOOL_STEP_ALIASES applies, e.g. build_project -> {build, apk})
        step_names = normalize_tool_names([tool_name])

        if success:
            for sn in step_names:
                if sn in plan.pending_steps:
                    plan.pending_steps.remove(sn)
                if isinstance(plan.completed_steps, list) and sn not in plan.completed_steps:
                    plan.completed_steps.append(sn)
        else:
            for sn in step_names:
                if sn not in plan.failed_steps:
                    plan.failed_steps.append(sn)

        plan.current_index += 1

    def get_missing_steps(self, plan_id: str) -> list[str]:
        """Return required steps not yet completed."""
        plan = self._plans.get(plan_id)
        if not plan:
            return []
        return plan.missing_steps

    def is_workflow_complete(self, plan_id: str) -> bool:
        """Check if all required steps are completed."""
        plan = self._plans.get(plan_id)
        if not plan:
            return True
        return plan.is_complete

    def check_early_termination(self, plan_id: str,
                                 completed_tool_names: list[str]) -> list[str]:
        """Detect if the model stopped before completing all required steps.

        Returns missing steps if early termination is detected, empty list otherwise.
        """
        plan = self._plans.get(plan_id)
        if not plan:
            return []

        missing = match_required_tools(plan.template_id, completed_tool_names)
        if missing:
            self._metrics["missing_steps_detected"] += len(missing)
            self._metrics["early_termination_prevented"] += 1
            logger.warning("Planner: early termination detected — missing steps: %s", missing)
        return missing

    def get_step_context(self, plan_id: str,
                         session_id: str | None = None) -> dict[str, Any] | None:
        """Get context for the next step to execute. Returns None if plan is complete."""
        plan = self._plans.get(plan_id)
        if not plan:
            return None

        if plan.current_index >= len(plan.steps):
            return None

        step = plan.steps[plan.current_index]
        return {
            "step_name": step["name"],
            "parameters": plan.parameters,
            "session_id": session_id or "",
        }

    def get_plan_id(self, goal: str) -> str | None:
        """Get the plan_id for a goal without creating a new plan."""
        template_id = classify(goal)
        if not template_id:
            return None
        return template_id

    def finalize(self, plan_id: str, success: bool) -> None:
        """Mark a plan as finalized and update metrics."""
        plan = self._plans.get(plan_id)
        if not plan:
            return
        if success:
            self._metrics["completed_workflows"] += 1
            self._metrics["workflow_completion_rate"] = int(
                (self._metrics["completed_workflows"] / max(self._metrics["total_workflows"], 1)) * 100
            )

    def get_task_for_step(self, plan_id: str, step_name: str) -> dict | None:
        """Resolve an abstract step name into executable task info.

        Returns dict with 'tool' (concrete tool name), 'step' (abstract name),
        and 'default_args' (fallback arguments) — or None if unmapable.
        """
        tool = STEP_TO_PRIMARY_TOOL.get(step_name)
        if not tool:
            return None

        plan = self._plans.get(plan_id)
        plan_params = plan.parameters if plan else {}

        default_args = dict(STEP_DEFAULT_ARGS.get(step_name, {}))
        # Inject plan-level parameters (extracted from goal) into defaults
        if step_name == "email" and "recipient" in plan_params:
            default_args["to"] = plan_params["recipient"]

        return {
            "tool": tool,
            "step": step_name,
            "default_args": default_args,
            "plan_params": plan_params,
        }

    async def inject_task(self, plan_id: str, step_name: str,
                           overrides: dict | None = None,
                           context: Any = None) -> dict:
        """Enforce a required workflow step by executing the mapped tool.

        The planner owns the decision to execute — this bypasses the LLM's
        choice gate. The caller may provide argument overrides (e.g. a specific
        URL or email recipient) which are merged on top of default_args.

        Returns the execution result dict.
        """
        task_info = self.get_task_for_step(plan_id, step_name)
        if not task_info:
            logger.error("Planner: cannot enforce unknown step=%s", step_name)
            return {"exit_code": 1, "error": f"Unknown step: {step_name}"}

        tool_name = task_info["tool"]
        default_args = task_info["default_args"]
        self._metrics["enforced_steps_executed"] = self._metrics.get("enforced_steps_executed", 0) + 1

        args = dict(default_args)
        if overrides:
            args.update(overrides)

        logger.info("Planner: enforcing step=%s -> tool=%s args=%s",
                     step_name, tool_name, args)

        from core.tools._constants import ToolBlock
        from core.tools.execution import execute_tool_block
        import json as _json
        block = ToolBlock(tool_type=tool_name, content=_json.dumps(args))
        _, result = await execute_tool_block(block, owner="dev")

        # Determine success: tools may signal via exit_code==0, sent=True,
        # success=True, status=ok, or absence of an "error" key.
        success = (
            result.get("exit_code", -1) == 0
            or result.get("sent") is True
            or result.get("success", False) is True
            or result.get("status") in ("ok", "success")
            or result.get("error") is None
        )
        self.record_step(plan_id, tool_name, success)

        if not success:
            self._metrics["enforced_steps_failed"] = self._metrics.get("enforced_steps_failed", 0) + 1
            logger.warning("Planner: enforced step=%s failed: %s", step_name, result.get("error", ""))

        return result
