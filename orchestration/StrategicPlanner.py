"""
Phase 11: TaskPlanner + AutonomousExecutor
Full integration of all phases into a coherent planning and execution system.

TaskPlanner:       Converts tasks/goals into structured plans
AutonomousExecutor: Executes plans using the action loop + verifier
"""

import asyncio
import json
import re
import uuid
from typing import Any, Dict, List, Optional
from core.context import TaskPlan, GenerationResult
from utils.logger import SystemLogger

logger = SystemLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# TASK PLANNER
# ═══════════════════════════════════════════════════════════════════

PLANNING_PROMPT = """You are an expert AI task planner. Create a detailed execution plan.

TASK: {task}
CONTEXT: {context}
SELF_ANALYSIS: {self_think}
PREDICTIONS: {predictions}

Create a comprehensive plan in JSON:
{{
  "goal": "precise goal statement",
  "strategy": "overall strategy name",
  "requires_debate": true/false,
  "requires_execution": true/false,
  "estimated_complexity": "low|medium|high|extreme",
  "sub_tasks": [
    {{
      "id": "st_1",
      "name": "task name",
      "description": "what to do",
      "depends_on": [],
      "tool": "optional tool name",
      "estimated_tokens": 500
    }}
  ],
  "required_agents": ["agent1", "agent2"],
  "required_tools": ["tool1", "tool2"],
  "constraints": [
    "no placeholders",
    "production-grade only"
  ],
  "success_criteria": [
    "criterion 1",
    "criterion 2"
  ]
}}

Rules:
- Sub-tasks must be atomic and independently verifiable
- No more than 10 sub-tasks for medium complexity
- Constraints must be specific and checkable
- Success criteria must be measurable
"""

GOAL_DECOMPOSITION_PROMPT = """Decompose this high-level goal into ordered sub-tasks for autonomous execution.

GOAL: {goal}

Each sub-task must be:
- Self-contained with a clear prompt
- Executable by an LLM agent
- Verifiable as complete

Respond in JSON:
{{
  "tasks": [
    {{
      "id": "task_1",
      "name": "Task name",
      "prompt": "Full prompt for the agent to execute this task",
      "depends_on": [],
      "success_metric": "How to know this task is done"
    }}
  ],
  "estimated_total_steps": N,
  "critical_path": ["task_1", "task_3", ...]
}}
"""

REPLAN_PROMPT = """A task has failed and we need to replan.

GOAL: {goal}
COMPLETED: {completed}
FAILED TASK: {failed_task}
FAILURE REASON: {failure_reason}

Generate a new set of tasks to recover and complete the goal.
Avoid repeating the failed approach.

Respond in JSON with same format as original plan (list of tasks).
"""


class TaskPlanner:
    """
    Converts tasks and goals into structured, executable plans.
    Integrates with meta-analysis for complexity estimation.
    """

    def __init__(self, model_router: Any, memory: Any):
        self.model_router = model_router
        self.memory = memory

    async def create_plan(
        self,
        task: str,
        self_think: Dict,
        predictions: Dict,
        context: Dict
    ) -> TaskPlan:
        """Create a structured execution plan for a task."""
        logger.info(f"[Planner] Creating plan for: {task[:60]}...")

        prompt = PLANNING_PROMPT.format(
            task=task,
            context=str(context.get("context", ""))[:300],
            self_think=str(self_think.get("structured", self_think))[:400],
            predictions=str(predictions.get("structured", predictions))[:300]
        )

        try:
            response = await self.model_router.complete(
                model="reasoning",
                prompt=prompt,
                temperature=0.3,
                max_tokens=2000
            )
            plan_dict = self._parse_json(response.get("text", ""))
        except Exception as e:
            logger.warning(f"[Planner] LLM planning failed: {e}, using heuristic")
            plan_dict = {}

        if not plan_dict:
            plan_dict = self._heuristic_plan(task, self_think, predictions)

        plan = TaskPlan(
            plan_id=str(uuid.uuid4())[:8],
            task=task,
            goal=plan_dict.get("goal", task),
            sub_tasks=plan_dict.get("sub_tasks", []),
            required_agents=plan_dict.get("required_agents", []),
            required_tools=plan_dict.get("required_tools", []),
            strategy=plan_dict.get("strategy", "direct"),
            requires_debate=plan_dict.get("requires_debate", False),
            requires_execution=plan_dict.get("requires_execution", False),
            estimated_complexity=plan_dict.get("estimated_complexity", "medium"),
            constraints=plan_dict.get("constraints", [
                "No placeholders or pseudocode",
                "Production-grade code only",
                "All edge cases handled"
            ]),
            success_criteria=plan_dict.get("success_criteria", [])
        )

        logger.info(
            f"[Planner] Plan created: {len(plan.sub_tasks)} subtasks | "
            f"complexity={plan.estimated_complexity} | debate={plan.requires_debate}"
        )
        return plan

    async def decompose_goal(self, goal: str) -> Dict[str, Any]:
        """Decompose a high-level goal into ordered sub-tasks for autonomous execution."""
        logger.info(f"[Planner] Decomposing goal: {goal[:60]}...")

        prompt = GOAL_DECOMPOSITION_PROMPT.format(goal=goal)

        try:
            response = await self.model_router.complete(
                model="reasoning",
                prompt=prompt,
                temperature=0.4,
                max_tokens=2000
            )
            result = self._parse_json(response.get("text", ""))
            if result and "tasks" in result:
                return result
        except Exception as e:
            logger.warning(f"[Planner] Decomposition failed: {e}")

        # Fallback: single task
        return {
            "tasks": [{
                "id": "task_1",
                "name": "Execute goal",
                "prompt": goal,
                "depends_on": [],
                "success_metric": "Goal completed"
            }],
            "estimated_total_steps": 1,
            "critical_path": ["task_1"]
        }

    async def replan(
        self, goal: str, completed: List[str],
        failed_task: Dict, result: Dict
    ) -> Dict[str, Any]:
        """Replan after a task failure."""
        logger.info(f"[Planner] Replanning after failure: {failed_task.get('name', 'unknown')}")

        prompt = REPLAN_PROMPT.format(
            goal=goal,
            completed=", ".join(completed[-5:]) or "None",
            failed_task=failed_task.get("name", "unknown"),
            failure_reason=str(result.get("error", "Low confidence"))[:200]
        )

        try:
            response = await self.model_router.complete(
                model="reasoning",
                prompt=prompt,
                temperature=0.5,
                max_tokens=1500
            )
            result = self._parse_json(response.get("text", ""))
            if result:
                if isinstance(result, list):
                    return {"tasks": result}
                if "tasks" in result:
                    return result
        except Exception as e:
            logger.warning(f"[Planner] Replan failed: {e}")

        # Fallback: retry with different approach
        return {
            "tasks": [{
                "id": f"retry_{uuid.uuid4().hex[:4]}",
                "name": f"Retry: {failed_task.get('name', 'task')}",
                "prompt": f"Previous attempt failed. Try a different approach: {failed_task.get('prompt', goal)}",
                "depends_on": [],
                "success_metric": "Task completed successfully"
            }]
        }

    def _heuristic_plan(self, task: str, self_think: Dict, predictions: Dict) -> Dict:
        """Generate a minimal plan when LLM planning fails."""
        complexity_hint = predictions.get("structured", {}).get("complexity_estimate", "medium")
        return {
            "goal": task,
            "strategy": "direct",
            "requires_debate": False,
            "requires_execution": any(
                w in task.lower()
                for w in ["run", "execute", "deploy", "test", "create file"]
            ),
            "estimated_complexity": complexity_hint,
            "sub_tasks": [{"id": "st_1", "name": "Complete task", "description": task}],
            "required_agents": [],
            "required_tools": [],
            "constraints": ["No placeholders", "Production-grade"],
            "success_criteria": ["Task fully completed"]
        }

    def _parse_json(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")
        return None


# ═══════════════════════════════════════════════════════════════════
# AUTONOMOUS EXECUTOR
# ═══════════════════════════════════════════════════════════════════

class AutonomousExecutor:
    """
    Executes a plan autonomously using the action loop.
    Handles verification, retries, and artifact collection.
    """

    def __init__(self, action_loop: Any, memory: Any, verifier: Any):
        self.action_loop = action_loop
        self.memory = memory
        self.verifier = verifier

    async def execute(
        self,
        plan: TaskPlan,
        generation: GenerationResult,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a plan. Returns execution result with artifacts and result text.
        """
        logger.info(f"[Executor] Executing plan: {plan.plan_id} | subtasks={len(plan.sub_tasks)}")

        if not plan.sub_tasks:
            # No sub-tasks: just use the generation output
            return {
                "executed": False,
                "result": generation.best_output,
                "artifacts": []
            }

        # Run the action loop
        loop_result = await self.action_loop.run(
            task=plan.task,
            plan=plan,
            context=context,
            generation=generation
        )

        # Store key artifacts in memory
        if loop_result.get("artifacts"):
            for artifact in loop_result["artifacts"]:
                await self.memory.store(
                    f"artifact:{artifact.get('name', uuid.uuid4().hex[:8])}",
                    artifact,
                    importance=0.8
                )

        return loop_result
