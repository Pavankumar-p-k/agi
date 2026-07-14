from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from brain.events.event_bus import Event, global_event_bus, EventBus
from brain.events.event_types import GoalAutoCreated
from core.planner.protocol import Plan, PlanStatus
from core.planner.unified_store import UnifiedStore
from brain.reasoning_engine import reasoning_engine
from brain.world_model import WorldModel

logger = logging.getLogger(__name__)

GOAL_GEN_SYSTEM = (
    "You are a proactive goal generator for an autonomous AI operating system.\n"
    "Given the current world state, identify opportunities for improvement\n"
    "or threats that need mitigation.\n"
    "Output a JSON array of goals, each with:\n"
    "  - objective: what needs to be done\n"
    "  - priority: 0-10 (10 = highest)\n"
    "  - reason: why this goal is important\n"
    "  - next_action: the first step to take\n"
    "Think inside <think> tags, output JSON inside <answer> tags."
)


class GoalGenerator:
    """Autonomous goal generation — detects opportunities and threats in
    the environment and creates goals without user input.

    Flow:
        Observe (WorldModel) -> Reason -> Create Goal -> Execute

    Examples:
      - Disk almost full -> Create cleanup goal
      - New file detected -> Create review/integrate goal
      - No activity for 1hr -> Create maintenance goal
      - Failed task repeated -> Create investigate/improve goal
    """

    def __init__(self, goal_manager: UnifiedStore, world_model: WorldModel,
                 event_bus: EventBus | None = None):
        self.goals = goal_manager
        self.world = world_model
        self.bus = event_bus or global_event_bus
        self._engine = reasoning_engine
        self._generated_count = 0

    async def evaluate_world(self) -> list[Plan]:
        """Observe the current world state and autonomously create goals.

        Returns newly created plans.
        """
        state = self.world.get_state()
        context = state.to_prompt_context()

        # Check for obvious conditions that don't need LLM
        new_goals: list[Plan] = []

        # Disk low -> cleanup goal
        if state.resources.disk_free_percent < 10.0 and state.resources.disk_free_percent > 0:
            goal = await self._create_goal(
                objective=f"Free disk space on {state.resources.disk_free_percent:.0f}% remaining",
                priority=8,
                reason=f"Disk critically low: {state.resources.disk_free_bytes / 1e9:.1f}GB free",
                next_action="Find and remove temporary files",
                source_observation=f"disk_free_percent={state.resources.disk_free_percent}",
            )
            new_goals.append(goal)

        # CPU high -> investigate goal
        if state.resources.cpu_percent > 90.0:
            goal = await self._create_goal(
                objective=f"Investigate high CPU usage ({state.resources.cpu_percent:.0f}%)",
                priority=7,
                reason="CPU usage exceeds 90% threshold, may indicate runaway process",
                next_action="List top CPU-consuming processes",
                source_observation=f"cpu_percent={state.resources.cpu_percent}",
            )
            new_goals.append(goal)

        # Use LLM for more complex goal generation
        llm_goals = await self._llm_goal_generation(context)
        new_goals.extend(llm_goals)

        await self.bus.publish(Event(
            type="goal.auto_created",
            source="goal_generator",
            payload=GoalAutoCreated(
                goal_id="batch",
                objective=f"Auto-generated {len(new_goals)} goals",
                reason="environment_evaluation",
                source_observation=context[:200],
            ).__dict__,
        ))

        self._generated_count += len(new_goals)
        return new_goals

    async def _create_goal(self, objective: str, priority: int,
                           reason: str, next_action: str,
                           source_observation: str) -> Plan:
        # Check if a similar goal already exists
        existing = self.goals.list_all(status="active", sort_by="priority")
        for g in existing:
            if objective[:50].lower() in g.goal.lower():
                logger.debug("[GoalGenerator] skipping duplicate: %s", objective[:60])
                return g

        goal = self.goals.create(
            goal=objective,
            priority=priority,
            next_action=next_action,
            tags=["auto_generated", "goal_generator"],
        )

        logger.info("[GoalGenerator] created goal: %s (priority=%d, reason=%s)",
                    objective[:80], priority, reason[:60])
        return goal

    async def _llm_goal_generation(self, context: str) -> list[Plan]:
        """Use LLM to detect opportunities/threats from world context."""
        try:
            result = await asyncio.wait_for(
                self._engine.reason(
                    "Analyze the current world state and suggest new goals.",
                    context,
                    system_override=GOAL_GEN_SYSTEM,
                ),
                timeout=15.0,
            )

            goals = self._parse_goals(result.answer)
            new_goals = []
            for g_data in goals:
                objective = g_data.get("objective", "").strip()
                if not objective:
                    continue
                priority = min(10, max(1, int(g_data.get("priority", 5))))
                reason = g_data.get("reason", "LLM analysis")
                next_action = g_data.get("next_action", "")

                goal = await self._create_goal(
                    objective=objective,
                    priority=priority,
                    reason=reason,
                    next_action=next_action,
                    source_observation=context[:200],
                )
                new_goals.append(goal)

            return new_goals

        except (asyncio.TimeoutError, Exception) as e:
            logger.exception("[GoalGenerator] LLM generation failed: %s", e)
            return []

    def _parse_goals(self, llm_output: str) -> list[dict]:
        import re
        answer_match = re.search(r"<answer>(.*?)</answer>", llm_output, re.DOTALL)
        json_str = answer_match.group(1).strip() if answer_match else llm_output.strip()
        json_str = re.sub(r"```(?:json)?\s*", "", json_str).strip()

        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            logger.warning("[GoalGenerator] JSON parse failed")
            return []

    @property
    def goals_generated(self) -> int:
        return self._generated_count
