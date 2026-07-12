from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.planner.protocol import Plan, PlanStatus
from core.storage import SYSTEM_DB

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS goals_plans (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    priority INTEGER NOT NULL DEFAULT 0,
    progress REAL NOT NULL DEFAULT 0.0,
    parent_plan_id TEXT,
    root_node TEXT NOT NULL DEFAULT '{}',
    blockers TEXT NOT NULL DEFAULT '[]',
    next_action TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    result TEXT NOT NULL DEFAULT '',
    deadline TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_MIGRATION_LOCK = threading.Lock()
_MIGRATION_DONE = False


class UnifiedStore:
    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or SYSTEM_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(_TABLE_SQL)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row_to_plan(self, row: sqlite3.Row) -> Plan:
        return Plan(
            id=row["id"],
            goal=row["goal"],
            status=PlanStatus(row["status"]),
            priority=row["priority"],
            progress=row["progress"],
            parent_plan_id=row["parent_plan_id"],
            root_node=json.loads(row["root_node"]) if row["root_node"] != "{}" else {},
            blockers=json.loads(row["blockers"]),
            next_action=row["next_action"],
            tags=json.loads(row["tags"]),
            result=row["result"],
            deadline=row["deadline"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, goal: str, priority: int = 0,
               parent_plan_id: str | None = None,
               root_node: dict[str, Any] | None = None,
               blockers: list[str] | None = None,
               next_action: str = "",
               tags: list[str] | None = None,
               deadline: str = "") -> Plan:
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        now = self._now()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO goals_plans
                   (id, goal, status, priority, progress, parent_plan_id, root_node,
                    blockers, next_action, tags, result, deadline, created_at, updated_at)
                   VALUES (?, ?, 'draft', ?, 0.0, ?, ?, ?, ?, ?, '', ?, ?, ?)""",
                (plan_id, goal, priority, parent_plan_id,
                 json.dumps(root_node or {}),
                 json.dumps(blockers or []),
                 next_action,
                 json.dumps(tags or []),
                 deadline, now, now),
            )
        logger.info("UnifiedStore: created plan %s for goal=%r", plan_id, goal[:60])
        return Plan(
            id=plan_id, goal=goal, status=PlanStatus.DRAFT,
            priority=priority, parent_plan_id=parent_plan_id,
            root_node=root_node, blockers=blockers or [],
            next_action=next_action, tags=tags or [],
            deadline=deadline, created_at=now, updated_at=now,
        )

    def get(self, plan_id: str) -> Plan | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM goals_plans WHERE id = ?", (plan_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_plan(row)

    def update(self, plan_id: str, **kwargs: Any) -> Plan | None:
        now = self._now()
        allowed = {"goal", "status", "priority", "progress",
                   "parent_plan_id", "next_action", "result", "deadline"}
        sets: list[str] = []
        values: list[Any] = []
        for key, value in kwargs.items():
            if key == "blockers":
                sets.append("blockers = ?")
                values.append(json.dumps(value))
            elif key == "tags":
                sets.append("tags = ?")
                values.append(json.dumps(value))
            elif key == "root_node":
                sets.append("root_node = ?")
                values.append(json.dumps(value))
            elif key == "status" and isinstance(value, PlanStatus):
                sets.append("status = ?")
                values.append(value.value)
            elif key in allowed:
                sets.append(f"{key} = ?")
                values.append(value)
        if not sets:
            return self.get(plan_id)
        sets.append("updated_at = ?")
        values.append(now)
        values.append(plan_id)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"UPDATE goals_plans SET {', '.join(sets)} WHERE id = ?",
                values,
            )
        logger.debug("UnifiedStore: updated plan %s", plan_id)
        return self.get(plan_id)

    def delete(self, plan_id: str) -> bool:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cur = conn.execute("DELETE FROM goals_plans WHERE id = ?", (plan_id,))
        return cur.rowcount > 0

    def list_all(self, status: str | None = None,
                 sort_by: str = "priority") -> list[Plan]:
        order = "priority DESC, created_at ASC"
        if sort_by == "created":
            order = "created_at DESC"
        elif sort_by == "progress":
            order = "progress ASC"
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    f"SELECT * FROM goals_plans WHERE status = ? ORDER BY {order}",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM goals_plans ORDER BY {order}"
                ).fetchall()
        return [self._row_to_plan(r) for r in rows]

    def count(self) -> dict[str, int]:
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM goals_plans").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM goals_plans WHERE status = 'active'"
            ).fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM goals_plans WHERE status = 'completed'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM goals_plans WHERE status = 'failed'"
            ).fetchone()[0]
        return {"total": total, "active": active,
                "completed": completed, "failed": failed}

    def get_highest_priority(self) -> Plan | None:
        plans = self.list_all(status="active", sort_by="priority")
        unblocked = [p for p in plans if not p.blockers]
        return (unblocked or plans)[0] if (unblocked or plans) else None

    def set_progress(self, plan_id: str, progress: float) -> Plan | None:
        progress = max(0.0, min(1.0, progress))
        return self.update(plan_id, progress=progress)

    def complete(self, plan_id: str, result: str = "") -> Plan | None:
        return self.update(
            plan_id, status=PlanStatus.COMPLETED, progress=1.0, result=result,
        )

    def fail(self, plan_id: str, reason: str = "") -> Plan | None:
        return self.update(plan_id, status=PlanStatus.FAILED, result=reason)

    def get_plan_tree(self, root_id: str | None = None) -> list[dict]:
        if root_id:
            root_plan = self.get(root_id)
            roots = [root_plan] if root_plan else []
        else:
            roots = self.list_all(status="active")

        def _build_tree(plan: Plan) -> dict:
            children = self.list_all()
            child_nodes = [
                _build_tree(c) for c in children
                if c.parent_plan_id == plan.id
            ]
            result = plan.to_dict()
            result["children"] = child_nodes
            return result

        return [_build_tree(r) for r in roots]

    def migrate_from_planstore(self) -> int:
        """Migrate all records from PlanStore's `plans` table into goals_plans."""
        count = 0
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT id, goal, status, root_node, created_at, updated_at FROM plans"
                ).fetchall()
            for row in rows:
                pid, goal, status, root_json, created, updated = row
                root = json.loads(root_json) if root_json != "{}" else {}
                with self._lock, sqlite3.connect(self._db_path) as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO goals_plans
                           (id, goal, status, root_node, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (pid, goal, status, json.dumps(root), created, updated),
                    )
                count += 1
            if count:
                logger.info("UnifiedStore: migrated %d plans from PlanStore", count)
        except Exception as e:
            logger.warning("UnifiedStore: PlanStore migration skipped (%s)", e)
        return count

    def migrate_from_goalmanager(self, gm_db_path: str) -> int:
        """Migrate all records from GoalManager's `goals` table into goals_plans."""
        count = 0
        try:
            with sqlite3.connect(gm_db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM goals").fetchall()
            for row in rows:
                plan = Plan.from_goal_dict(dict(row))
                with self._lock, sqlite3.connect(self._db_path) as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO goals_plans
                           (id, goal, status, priority, progress, parent_plan_id, root_node,
                            blockers, next_action, tags, result, deadline, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (plan.id, plan.goal, plan.status.value, plan.priority,
                         plan.progress, plan.parent_plan_id, json.dumps(plan.root_node or {}),
                         json.dumps(plan.blockers), plan.next_action,
                         json.dumps(plan.tags), plan.result, plan.deadline,
                         plan.created_at, plan.updated_at),
                    )
                count += 1
            if count:
                logger.info("UnifiedStore: migrated %d goals from GoalManager", count)
        except Exception as e:
            logger.warning("UnifiedStore: GoalManager migration skipped (%s)", e)
        return count


def run_migrations(store: UnifiedStore | None = None,
                   gm_db_path: str | None = None) -> None:
    global _MIGRATION_DONE
    if _MIGRATION_DONE:
        return
    with _MIGRATION_LOCK:
        if _MIGRATION_DONE:
            return
        s = store or UnifiedStore()
        s.migrate_from_planstore()
        if gm_db_path:
            s.migrate_from_goalmanager(gm_db_path)
        _MIGRATION_DONE = True
