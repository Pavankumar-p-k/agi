from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .goal import Goal, GoalStatus

logger = logging.getLogger(__name__)


class GoalManager:
    """Persistent goal manager — CRUD + prioritization + progress tracking.

    Goals are stored in SQLite and support hierarchical parent-child relationships,
    blocker tracking, and priority-based ordering.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    progress REAL NOT NULL DEFAULT 0.0,
                    priority INTEGER NOT NULL DEFAULT 0,
                    parent_goal_id TEXT,
                    blockers TEXT NOT NULL DEFAULT '[]',
                    next_action TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    result TEXT NOT NULL DEFAULT '',
                    deadline TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_goals_status
                ON goals(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_goals_priority
                ON goals(priority DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_goals_parent
                ON goals(parent_goal_id)
            """)
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_goal(self, row: sqlite3.Row) -> Goal:
        return Goal(
            id=row["id"],
            objective=row["objective"],
            status=GoalStatus(row["status"]),
            progress=row["progress"],
            priority=row["priority"],
            parent_goal_id=row["parent_goal_id"],
            blockers=json.loads(row["blockers"]),
            next_action=row["next_action"],
            tags=json.loads(row["tags"]),
            result=row["result"],
            deadline=row["deadline"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, objective: str, priority: int = 0,
               parent_goal_id: str | None = None,
               blockers: list[str] | None = None,
               next_action: str = "",
               tags: list[str] | None = None,
               deadline: str = "") -> Goal:
        goal_id = str(uuid.uuid4())
        now = self._now()

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO goals
                   (id, objective, status, progress, priority, parent_goal_id,
                    blockers, next_action, tags, result, deadline, created_at, updated_at)
                   VALUES (?, ?, 'active', 0.0, ?, ?, ?, ?, ?, '', ?, ?, ?)""",
                (goal_id, objective, priority, parent_goal_id,
                 json.dumps(blockers or []),
                 next_action,
                 json.dumps(tags or []),
                 deadline, now, now),
            )
            conn.commit()
            conn.close()

        goal = Goal(
            id=goal_id,
            objective=objective,
            status=GoalStatus.ACTIVE,
            progress=0.0,
            priority=priority,
            parent_goal_id=parent_goal_id,
            blockers=blockers or [],
            next_action=next_action,
            tags=tags or [],
            deadline=deadline,
            created_at=now,
            updated_at=now,
        )
        logger.info("[GoalManager] created goal %s: %s", goal_id, objective[:80])
        return goal

    def get(self, goal_id: str) -> Goal | None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM goals WHERE id = ?", (goal_id,)
            ).fetchone()
            conn.close()

        if not row:
            return None
        return self._row_to_goal(row)

    def update(self, goal_id: str, **kwargs) -> Goal | None:
        now = self._now()
        allowed = {"objective", "status", "progress", "priority",
                   "parent_goal_id", "next_action", "result", "deadline"}

        from brain.goals.goal import GoalStatus as GS

        sets = []
        values = []
        for key, value in kwargs.items():
            if key == "blockers":
                sets.append("blockers = ?")
                values.append(json.dumps(value))
                continue
            if key == "tags":
                sets.append("tags = ?")
                values.append(json.dumps(value))
                continue
            if key in allowed:
                if key == "status" and isinstance(value, GS):
                    value = value.value
                sets.append(f"{key} = ?")
                values.append(value)

        if not sets:
            return self.get(goal_id)

        sets.append("updated_at = ?")
        values.append(now)
        values.append(goal_id)

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                f"UPDATE goals SET {', '.join(sets)} WHERE id = ?",
                values,
            )
            conn.commit()
            conn.close()

        logger.debug("[GoalManager] updated goal %s", goal_id)
        return self.get(goal_id)

    def delete(self, goal_id: str) -> bool:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            deleted = cur.rowcount
            conn.commit()
            conn.close()
        return deleted > 0

    def list_active(self, sort_by: str = "priority") -> list[Goal]:
        return self._list(status=GoalStatus.ACTIVE, sort_by=sort_by)

    def list_by_status(self, status: GoalStatus | str, sort_by: str = "priority") -> list[Goal]:
        if isinstance(status, GoalStatus):
            status = status.value
        return self._list(status=status, sort_by=sort_by)

    def _list(self, status: str | None = None, sort_by: str = "priority") -> list[Goal]:
        order = "priority DESC, created_at ASC"
        if sort_by == "created":
            order = "created_at DESC"
        elif sort_by == "progress":
            order = "progress ASC"

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    f"SELECT * FROM goals WHERE status = ? ORDER BY {order}",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM goals ORDER BY {order}"
                ).fetchall()
            conn.close()

        return [self._row_to_goal(r) for r in rows]

    def get_highest_priority(self) -> Goal | None:
        goals = self.list_active(sort_by="priority")
        if not goals:
            return None
        # Return the first active goal with no blockers first
        unblocked = [g for g in goals if not g.blockers]
        if unblocked:
            return unblocked[0]
        return goals[0] if goals else None

    def add_blocker(self, goal_id: str, blocker: str) -> Goal | None:
        goal = self.get(goal_id)
        if not goal:
            return None
        if blocker not in goal.blockers:
            goal.blockers.append(blocker)
            self.update(goal_id, blockers=goal.blockers)
        return self.get(goal_id)

    def remove_blocker(self, goal_id: str, blocker: str) -> Goal | None:
        goal = self.get(goal_id)
        if not goal:
            return None
        if blocker in goal.blockers:
            goal.blockers.remove(blocker)
            self.update(goal_id, blockers=goal.blockers)
        return self.get(goal_id)

    def set_progress(self, goal_id: str, progress: float) -> Goal | None:
        progress = max(0.0, min(1.0, progress))
        return self.update(goal_id, progress=progress)

    def complete(self, goal_id: str, result: str = "") -> Goal | None:
        return self.update(
            goal_id,
            status=GoalStatus.COMPLETED,
            progress=1.0,
            result=result,
        )

    def fail(self, goal_id: str, reason: str = "") -> Goal | None:
        return self.update(
            goal_id,
            status=GoalStatus.FAILED,
            result=reason,
        )

    def get_goal_tree(self, root_id: str | None = None) -> list[dict]:
        """Return hierarchical tree of goals."""
        if root_id:
            roots = [self.get(root_id)] if self.get(root_id) else []
        else:
            roots = self.list_active()

        def _build_tree(goal: Goal) -> dict:
            children = self._list(status=None)
            child_nodes = [
                _build_tree(c) for c in children
                if c.parent_goal_id == goal.id
            ]
            return {**goal.to_dict(), "children": child_nodes}

        return [_build_tree(g) for g in roots]

    def count(self) -> dict:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            total = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM goals WHERE status = 'active'"
            ).fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM goals WHERE status = 'completed'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM goals WHERE status = 'failed'"
            ).fetchone()[0]
            conn.close()
        return {
            "total": total,
            "active": active,
            "completed": completed,
            "failed": failed,
        }
