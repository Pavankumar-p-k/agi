from __future__ import annotations

import logging
from typing import Any

from brain.events.event_bus import Event, global_event_bus
from brain.events.event_types import LearningApplied
from core.planner.unified_store import UnifiedStore
from memory.memory_facade import memory as _memory_facade

logger = logging.getLogger(__name__)


class LearningEngine:
    """Learning engine — automatically modifies future behavior from stored lessons.

    Instead of just storing "what worked" and "what failed", this engine
    actively changes planning prompts, execution parameters, and decision
    weights based on accumulated lessons in DecisionMemory.

    Flow:
        Memory (DecisionMemory) -> LearningEngine -> Behavior Modification
                                                       │
                                                       └──> Planning prompt tweaks
                                                       └──> Executor parameter changes
                                                       └──> Subsystem configuration
    """

    def __init__(self, memory_manager=None,
                 goal_manager: UnifiedStore | None = None):
        self.memory = memory_manager or _memory_facade
        self.goals = goal_manager
        self._lesson_prompt_suffix: str = ""
        self._suppressed_actions: set[str] = set()
        self._preferred_actions: set[str] = set()
        self._last_refresh_count: int = 0

    async def refresh(self) -> int:
        """Read all lessons from DecisionMemory and update behavior.

        Returns the number of new lessons applied.
        """
        failures = self.memory.get_failures(limit=50, user_id="brain")
        lessons = self.memory.get_lessons(limit=50, user_id="brain")

        new_count = len(failures) + len(lessons)
        if new_count == self._last_refresh_count and self._lesson_prompt_suffix:
            return 0

        # Build lesson prompt suffix
        prompt_parts = []

        if failures:
            prompt_parts.append("Lessons from past failures:")
            for f in failures[:10]:
                lesson = f.get("lesson", "").strip()
                context = f.get("context", "")[:80]
                if lesson:
                    prompt_parts.append(f"  - [{context}]: {lesson}")

        if lessons:
            prompt_parts.append("\nSuccessful patterns:")
            for l in lessons[:10]:
                lesson = l.get("lesson", "").strip()
                if lesson and l.get("success"):
                    prompt_parts.append(f"  - {lesson}")

        if prompt_parts:
            self._lesson_prompt_suffix = "\n\n" + "\n".join(prompt_parts)
        else:
            self._lesson_prompt_suffix = ""

        # Extract suppressed/preferred actions
        self._suppressed_actions.clear()
        self._preferred_actions.clear()
        for f in failures:
            action = self._extract_action(f.get("decision", ""))
            if action and not f.get("success"):
                self._suppressed_actions.add(action)
        for l in lessons:
            action = self._extract_action(l.get("decision", ""))
            if action and l.get("success"):
                self._preferred_actions.add(action)

        self._last_refresh_count = new_count

        if prompt_parts:
            await global_event_bus.publish(Event(
                type="learning.applied",
                source="learning_engine",
                payload=LearningApplied(
                    lesson_count=len(prompt_parts),
                    affected_subsystems=["planning"],
                ).__dict__,
            ))
            logger.info("[LearningEngine] applied %d lessons, %d suppressed, %d preferred",
                        len(prompt_parts), len(self._suppressed_actions), len(self._preferred_actions))

        return len(prompt_parts)

    def _extract_action(self, decision: str) -> str:
        """Extract an action name from a decision string."""
        if not decision:
            return ""
        return decision.strip().lower()

    def get_prompt_suffix(self) -> str:
        """Return the learning-based prompt suffix for LLM calls.

        Append this to planning/reasoning prompts to guide the LLM
        away from past failures and toward past successes.
        """
        return self._lesson_prompt_suffix

    def should_suppress(self, action_name: str) -> bool:
        """Check if an action should be avoided based on past failures."""
        return action_name.lower() in self._suppressed_actions

    def should_prefer(self, action_name: str) -> bool:
        """Check if an action should be preferred based on past success."""
        return action_name.lower() in self._preferred_actions

    async def auto_improve(self) -> dict:
        """Run full learning cycle: refresh lessons, adjust goal priorities,
        suggest plan modifications."""
        lessons_applied = await self.refresh()

        suggestions = []

        # If we have suppressed actions, suggest goal adjustments
        if self._suppressed_actions and self.goals:
            active = self.goals.list_all(status="active", sort_by="priority")[:5]
            for goal in active:
                for suppressed in self._suppressed_actions:
                    if suppressed in goal.next_action.lower():
                        suggestions.append({
                            "goal_id": goal.id,
                            "suggestion": f"Avoid '{suppressed}' — past failures recorded. Consider alternative approach.",
                            "type": "plan_adjustment",
                        })

        return {
            "lessons_applied": lessons_applied,
            "suppressed_actions": list(self._suppressed_actions),
            "preferred_actions": list(self._preferred_actions),
            "suggestions": suggestions,
        }


learning_engine: LearningEngine | None = None
