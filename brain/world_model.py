from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.planner.unified_store import UnifiedStore
from brain.executor import executor
from memory.memory_facade import memory as _memory_facade

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """A known entity in the world (person, service, application, device)."""
    id: str = ""
    name: str = ""
    type: str = "unknown"
    properties: dict = field(default_factory=dict)
    last_seen: str = ""


@dataclass
class ResourceState:
    """Current resource utilization."""
    disk_free_percent: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_free_bytes: int = 0
    disk_total_bytes: int = 0


@dataclass
class WorldState:
    """Complete snapshot of the AI's world at a point in time.

    The AI reasons over this model instead of isolated prompts,
    giving it situational awareness.
    """
    goals: list[dict] = field(default_factory=list)
    task_graphs: dict = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    resources: ResourceState = field(default_factory=ResourceState)
    memory_summary: dict = field(default_factory=dict)
    event_stats: dict = field(default_factory=dict)
    timestamp: str = ""

    def to_prompt_context(self) -> str:
        """Format the world state as a prompt context string for LLM reasoning."""
        lines = ["=== World State ==="]
        lines.append(f"Time: {self.timestamp}")

        lines.append(f"\nActive Goals ({len(self.goals)}):")
        for g in self.goals:
            blockers = g.get("blockers", [])
            blocker_str = f" BLOCKED: {blockers}" if blockers else ""
            lines.append(f"  - [{g['status']}] {g['objective'][:80]} ({g['progress']:.0%}){blocker_str}")

        if self.entities:
            lines.append(f"\nKnown Entities ({len(self.entities)}):")
            for eid, ent in self.entities.items():
                lines.append(f"  - {ent.name} ({ent.type})")

        lines.append(f"\nResources: disk={self.resources.disk_free_percent:.0f}% free, "
                     f"cpu={self.resources.cpu_percent:.0f}%, "
                     f"mem={self.resources.memory_percent:.0f}%")

        if self.memory_summary:
            ms = self.memory_summary
            lines.append(f"\nMemory: {ms.get('semantic_count', 0)} facts, "
                         f"{ms.get('episodic_count', 0)} episodes, "
                         f"{ms.get('decision_count', 0)} decisions, "
                         f"{ms.get('task_count', 0)} traces")

        return "\n".join(lines)


class WorldModel:
    """Central world model — tracks everything the AI knows about its environment.

    Updated continuously by observers and subsystems. Provides structured
    context for LLM reasoning so the AI has situational awareness instead
    of operating on isolated prompts.
    """

    def __init__(self, goal_manager: UnifiedStore | None = None,
                 memory_manager=None):
        self.goals = goal_manager
        self.memory = memory_manager or _memory_facade
        self._entities: dict[str, Entity] = {}
        self._tools_cache: list[dict] = []

    def register_entity(self, entity: Entity):
        entity.last_seen = datetime.now(timezone.utc).isoformat()
        self._entities[entity.id or entity.name] = entity
        logger.debug("[WorldModel] entity registered: %s (%s)", entity.name, entity.type)

    def remove_entity(self, entity_id: str):
        self._entities.pop(entity_id, None)

    def get_entity(self, name_or_id: str) -> Entity | None:
        return self._entities.get(name_or_id)

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        return [e for e in self._entities.values() if e.type == entity_type]

    def update_resources(self, resources: ResourceState):
        self._resources = resources

    def get_state(self) -> WorldState:
        """Take a snapshot of the current world state."""
        now = datetime.now(timezone.utc).isoformat()

        goal_list = []
        if self.goals:
            for g in self.goals.list_all(status="active", sort_by="priority")[:20]:
                goal_list.append(g.to_dict())

        resources = ResourceState()
        try:
            if hasattr(os, 'statvfs'):
                for path in self._get_mount_points():
                    try:
                        usage = os.statvfs(path)
                        free = usage.f_frsize * usage.f_bavail
                        total = usage.f_frsize * usage.f_blocks
                        if total > 0:
                            resources.disk_free_percent = (free / total) * 100
                            resources.disk_free_bytes = free
                            resources.disk_total_bytes = total
                    except OSError:
                        continue
        except Exception:
            pass

        try:
            import psutil
            resources.cpu_percent = psutil.cpu_percent(interval=0.1)
            resources.memory_percent = psutil.virtual_memory().percent
        except ImportError:
            pass

        mem_summary = self.memory.summarize(user_id="brain")
        event_stats = {}

        return WorldState(
            goals=goal_list,
            entities=dict(self._entities),
            tools=list(self._tools_cache),
            resources=resources,
            memory_summary=mem_summary,
            event_stats=event_stats,
            timestamp=now,
        )

    def get_context_for_llm(self) -> str:
        """Get a formatted string describing the world state for LLM prompts."""
        return self.get_state().to_prompt_context()

    def _get_mount_points(self) -> list[str]:
        if os.name == "nt":
            drives = []
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append(drive)
            return drives
        return ["/"]

    def refresh_tools(self):
        """Refresh the cached tool list from the executor."""
        from brain.executor import executor
        self._tools_cache = [
            {"name": name, "type": type(tool).__name__}
            for name, tool in executor._tools.items()
        ]


import os
