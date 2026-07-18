"""PlanStore — SQLite-backed persistence for plans.

Each plan stores a serialized goal decomposition tree (PlanNode) with
lifecycle status (draft → approved → executing → completed/failed).
Lives in data/planner.db as part of the planner bounded context.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.planner.models import SubGoal
from core.storage import PLANNER_DB

logger = logging.getLogger(__name__)

_DEFAULT_DB = PLANNER_DB

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    root_node TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class PlanStore:
    """SQLite-backed persistence for plans.

    Thread-safe. Each CRUD method opens its own connection.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(_TABLE_SQL)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(self, goal: str, root_node: dict[str, Any] | None = None) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        node = root_node or _default_decomposition(goal)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO plans (id, goal, status, root_node, created_at, updated_at)
                   VALUES (?, ?, 'draft', ?, ?, ?)""",
                (plan_id, goal, json.dumps(node), now, now),
            )
        logger.info("PlanStore: created plan %s for goal=%r", plan_id, goal[:60])
        return self._build_plan(plan_id, goal, "draft", node, now, now)

    def get(self, plan_id: str) -> dict[str, Any] | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT id, goal, status, root_node, created_at, updated_at FROM plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        if not row:
            return None
        return self._build_plan(*row)

    def list_all(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT id, goal, status, root_node, created_at, updated_at FROM plans WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, goal, status, root_node, created_at, updated_at FROM plans ORDER BY created_at DESC"
                ).fetchall()
        return [self._build_plan(*r) for r in rows]

    def update_status(self, plan_id: str, status: str) -> bool:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE plans SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, plan_id),
            )
        return cur.rowcount > 0

    def update_node(self, plan_id: str, node_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        plan = self.get(plan_id)
        if not plan:
            return None

        def _apply(node: dict[str, Any]) -> bool:
            if node.get("id") == node_id:
                for k, v in patch.items():
                    if k != "id":
                        node[k] = v
                return True
            for child in node.get("children", []):
                if _apply(child):
                    return True
            return False

        root = plan["root_node"]
        if not _apply(root):
            return None

        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE plans SET root_node = ?, updated_at = ? WHERE id = ?",
                (json.dumps(root), now, plan_id),
            )
        plan["root_node"] = root
        plan["updated_at"] = now
        return plan

    def delete(self, plan_id: str) -> bool:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cur = conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        return cur.rowcount > 0

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_plan(
        plan_id: str,
        goal: str,
        status: str,
        root_node_json: str | dict,
        created_at: str,
        updated_at: str,
    ) -> dict[str, Any]:
        if isinstance(root_node_json, str):
            root = json.loads(root_node_json)
        else:
            root = root_node_json
        return {
            "id": plan_id,
            "goal": goal,
            "status": status,
            "root_node": root,
            "created_at": created_at,
            "updated_at": updated_at,
        }


def _default_decomposition(goal: str) -> dict[str, Any]:
    """Generate an initial decomposition from a goal using the GoalDecomposer."""
    try:
        from core.planner.decomposer import GoalDecomposer
        decomposer = GoalDecomposer()
        subgoal = decomposer.decompose(goal)
        result = _subgoal_to_dict(subgoal)
        result["id"] = "root"  # stable root id for UI
        return result
    except Exception as e:
        logger.warning("PlanStore: decomposition failed, using flat plan: %s", e)
        return {
            "id": "root",
            "title": goal[:120],
            "description": goal,
            "assigned_agent": None,
            "estimated_duration": None,
            "priority": 0,
            "status": "pending",
            "children": [],
        }


def _subgoal_to_dict(sg: SubGoal) -> dict[str, Any]:
    return {
        "id": sg.id,
        "title": sg.description[:80],
        "description": sg.description,
        "assigned_agent": sg.agent_id,
        "estimated_duration": None,
        "priority": 0,
        "status": sg.status,
        "children": [_subgoal_to_dict(c) for c in sg.children],
    }
