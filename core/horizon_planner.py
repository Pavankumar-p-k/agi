"""core/horizon_planner.py
HorizonPlanner — long-term goal planning with milestone tracking.
Goals stored as JSON files under ~/.jarvis/horizon_goals/.
"""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path.home() / ".jarvis" / "horizon_goals"


@dataclass
class Milestone:
    id: str = ""
    description: str = ""
    success_criteria: str = ""
    completed: bool = False


@dataclass
class HorizonGoal:
    goal_id: str = ""
    description: str = ""
    domain: str = ""
    horizon: str = "weekly"
    milestones: list[Milestone] = field(default_factory=list)
    deadline: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def progress(self) -> float:
        if not self.milestones:
            return 0.0
        done = sum(1 for m in self.milestones if m.completed)
        return done / len(self.milestones)


class HorizonPlanner:

    def __init__(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, HorizonGoal] = {}

    def _path(self, goal_id: str) -> Path:
        return BASE_DIR / f"{goal_id}.json"

    def create(self, description: str, domain: str, horizon: str = "weekly", deadline: str = "") -> HorizonGoal:
        now = datetime.utcnow().isoformat()
        goal = HorizonGoal(
            goal_id=uuid.uuid4().hex[:12],
            description=description,
            domain=domain,
            horizon=horizon,
            deadline=deadline,
            created_at=now,
            updated_at=now,
            milestones=[Milestone(id="m1", description="Define goal", success_criteria="Goal is clearly defined")],
        )
        self._save(goal)
        return goal

    def _save(self, goal: HorizonGoal) -> None:
        self._cache[goal.goal_id] = goal
        self._path(goal.goal_id).write_text(json.dumps({
            "goal_id": goal.goal_id,
            "description": goal.description,
            "domain": goal.domain,
            "horizon": goal.horizon,
            "deadline": goal.deadline,
            "notes": goal.notes,
            "created_at": goal.created_at,
            "updated_at": goal.updated_at,
            "milestones": [{"id": m.id, "description": m.description,
                            "success_criteria": m.success_criteria, "completed": m.completed}
                           for m in goal.milestones],
        }, indent=2, default=str))

    def load(self, goal_id: str) -> Optional[HorizonGoal]:
        if goal_id in self._cache:
            return self._cache[goal_id]
        path = self._path(goal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            goal = HorizonGoal(
                goal_id=data["goal_id"],
                description=data.get("description", ""),
                domain=data.get("domain", ""),
                horizon=data.get("horizon", "weekly"),
                deadline=data.get("deadline", ""),
                notes=data.get("notes", ""),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                milestones=[Milestone(**m) for m in data.get("milestones", [])],
            )
            self._cache[goal_id] = goal
            return goal
        except Exception as e:
            logger.warning("[HORIZON] Corrupted goal file %s: %s", goal_id, e)
            return None

    def list(self, domain: Optional[str] = None) -> list[HorizonGoal]:
        goals = []
        for path in sorted(BASE_DIR.glob("*.json")):
            gid = path.stem
            goal = self.load(gid)
            if goal and (domain is None or goal.domain == domain):
                goals.append(goal)
        return goals

    def delete(self, goal_id: str) -> bool:
        self._cache.pop(goal_id, None)
        path = self._path(goal_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def advance(self, goal_id: str) -> Optional[HorizonGoal]:
        goal = self.load(goal_id)
        if goal is None:
            return None
        for m in goal.milestones:
            if not m.completed:
                m.completed = True
                break
        goal.updated_at = datetime.utcnow().isoformat()
        self._save(goal)
        return goal

    def get_approaching_deadlines(self, days_ahead: int = 3) -> list[HorizonGoal]:
        now = datetime.utcnow()
        approaching = []
        for goal in self.list():
            if goal.deadline:
                try:
                    deadline = datetime.fromisoformat(goal.deadline)
                    if 0 <= (deadline - now).days <= days_ahead:
                        approaching.append(goal)
                except Exception as e:
                    logger.exception("[HORIZON] Deadline parse failed: %s", e)
        return approaching


import logging
logger = logging.getLogger("horizon")

horizon_planner: HorizonPlanner | None = None
