from __future__ import annotations

import json
import logging
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brain.events.event_bus import Event, global_event_bus
from brain.events.event_types import LearningApplied
from brain.memory.memory_manager import MemoryManager
from brain.goals.goal_manager import GoalManager
from brain.tools.project_tool import project_tool

logger = logging.getLogger(__name__)


@dataclass
class SkillTemplate:
    """A reusable workflow extracted from repeated action patterns."""
    id: str = ""
    name: str = ""
    description: str = ""
    actions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: str = ""
    usage_count: int = 0
    success_rate: float = 0.0
    skill_file_path: str | None = None


class SkillAcquisition:
    """Discovers reusable workflows from repeated action patterns.

    The system observes task execution traces, detects repeated
    action sequences, and registers them as reusable skills.

    Flow:
        Observe repeated actions
        → Detect pattern (e.g., "create file → write file → compile → test")
        → Create reusable workflow
        → Register as skill
        → Use automatically when similar task detected next time
    """

    def __init__(self, memory_manager: MemoryManager,
                 goal_manager: GoalManager | None = None):
        self.memory = memory_manager
        self.goals = goal_manager
        self._skills: dict[str, SkillTemplate] = {}
        self._action_sequences: dict[str, list[list[str]]] = defaultdict(list)
        self._discovery_count = 0

    async def analyze_recent_traces(self, n_hours: int = 24) -> list[SkillTemplate]:
        """Scan recent TaskMemory for repeated action patterns.

        Returns newly discovered skill templates.
        """
        traces = self.memory.task.get_recent(limit=500)
        if len(traces) < 5:
            return []

        # Group traces by task_id (goal)
        task_groups: dict[str, list[dict]] = defaultdict(list)
        for t in traces:
            tid = t.get("task_id", "unknown")
            task_groups[tid].append(t)

        # Extract action sequences per task
        for task_id, task_traces in task_groups.items():
            sequence = [t.get("action_name", "") for t in sorted(
                task_traces, key=lambda x: x.get("created_at", "")
            ) if t.get("action_name")]
            if len(sequence) >= 3:
                key = task_id[:20]
                if sequence not in self._action_sequences.get(key, []):
                    self._action_sequences[key].append(sequence)

        # Find common patterns across tasks
        all_sequences = []
        for seqs in self._action_sequences.values():
            all_sequences.extend(seqs)

        if len(all_sequences) < 3:
            return []

        # Find frequent N-grams (subsequences of length 3-4)
        patterns = self._find_frequent_patterns(all_sequences, min_support=2)

        new_skills = []
        for pattern, count in patterns:
            skill = await self._register_skill_from_pattern(pattern, count)
            if skill:
                new_skills.append(skill)

        if new_skills:
            await global_event_bus.publish(Event(
                type="learning.applied",
                source="skill_acquisition",
                payload=LearningApplied(
                    lesson_count=len(new_skills),
                    affected_subsystems=["skills"],
                ).__dict__,
            ))

        return new_skills

    def _find_frequent_patterns(self, sequences: list[list[str]],
                                min_support: int = 2,
                                n: int = 3) -> list[tuple[tuple[str, ...], int]]:
        """Find frequent subsequences of length n across multiple action sequences.

        Uses simple N-gram counting over action names.
        """
        ngram_counts: Counter[tuple[str, ...]] = Counter()

        for seq in sequences:
            if len(seq) < n:
                continue
            for i in range(len(seq) - n + 1):
                ngram = tuple(seq[i:i + n])
                ngram_counts[ngram] += 1

        # Return patterns that appear in multiple sequences
        return [
            (ngram, count)
            for ngram, count in ngram_counts.most_common(20)
            if count >= min_support
        ]

    async def _register_skill_from_pattern(self, pattern: tuple[str, ...],
                                           count: int) -> SkillTemplate | None:
        """Convert a detected action pattern into a reusable skill."""
        pattern_str = " -> ".join(pattern)
        name = f"auto_{pattern[0][:20]}_workflow"

        # Check if this pattern is already registered as a skill
        for existing in self._skills.values():
            if existing.name == name:
                existing.usage_count += 1
                existing.confidence = min(1.0, existing.confidence + 0.1)
                return None

        # Create skill file (generate id first so we can reference it in the file)
        skill_id = str(uuid.uuid4())
        skill_path = await self._write_skill_file(name, pattern, pattern_str, skill_id)
        if not skill_path:
            return None

        skill = SkillTemplate(
            id=skill_id,
            name=name,
            description=f"Auto-discovered workflow: {pattern_str} (appeared {count}x)",
            actions=list(pattern),
            confidence=0.5,
            usage_count=1,
            success_rate=0.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            skill_file_path=skill_path,
        )

        self._skills[skill.id] = skill
        self._discovery_count += 1

        logger.info("[SkillAcquisition] discovered skill '%s': %s (count=%d)",
                    name, pattern_str, count)
        return skill

    async def _write_skill_file(self, name: str, pattern: tuple[str, ...],
                                pattern_str: str, skill_id: str) -> str | None:
        """Write a skill markdown file to the skills directory."""
        import os
        skills_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
        )
        os.makedirs(skills_dir, exist_ok=True)

        steps_yaml = "\n".join(f"    - {a}" for a in pattern)

        content = f"""---
name: "{name}"
description: "Auto-discovered workflow: {pattern_str}"
triggers:
  - pattern: "{pattern[0]}"
  - pattern: "{pattern[0]}.*"
---

# {name}

Auto-discovered from repeated execution patterns.

## Steps
{steps_yaml}

## Usage
This skill was automatically generated by the SkillAcquisition engine.
It was detected because the action sequence appeared in multiple task executions.
"""

        filepath = os.path.join(skills_dir, f"{name}.md")
        try:
            async with asyncio.Lock():
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
            return filepath
        except OSError as e:
            logger.warning("[SkillAcquisition] failed to write skill file: %s", e)
            return None

    def get_skills(self) -> list[SkillTemplate]:
        return list(self._skills.values())

    def suggest_skill(self, action_name: str) -> SkillTemplate | None:
        """Find a skill that matches the given action."""
        for skill in self._skills.values():
            if skill.actions and skill.actions[0] == action_name:
                return skill
        return None

    def get_stats(self) -> dict:
        return {
            "skills_discovered": self._discovery_count,
            "active_skills": len(self._skills),
            "sequences_tracked": sum(len(v) for v in self._action_sequences.values()),
        }


import asyncio
