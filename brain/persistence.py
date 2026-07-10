from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brain.goals.goal_manager import GoalManager
from core.planner.dag import TaskGraph

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """A full system state snapshot for multi-day persistence."""
    id: str = ""
    goal_id: str = ""
    goal_data: dict = field(default_factory=dict)
    task_graph_data: dict = field(default_factory=dict)
    project_path: str = ""
    architecture_decisions: list = field(default_factory=list)
    context_summary: str = ""
    created_at: str = ""


@dataclass
class DecisionRecord:
    """An architecture or design decision recorded in the journal."""
    id: str = ""
    goal_id: str = ""
    title: str = ""
    decision: str = ""
    alternatives: list = field(default_factory=list)
    rationale: str = ""
    outcome: str = ""
    created_at: str = ""


class ProjectPersistence:
    """Multi-day checkpoint/resume for long-running autonomous projects.

    The test:
        Day 1: Build Android App
        Day 5: Resume automatically
        Day 20: Still remembers architecture decisions

    This stores:
        - Full project state (goals, DAGs, progress)
        - Architecture decision journal
        - Checkpoint history for rollback
        - Context summary for LLM re-hydration
    """

    def __init__(self, db_path: str, goal_manager: GoalManager | None = None):
        self._db_path = db_path
        self.goals = goal_manager
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_checkpoints (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    goal_data TEXT NOT NULL,
                    task_graph_data TEXT NOT NULL DEFAULT '{}',
                    project_path TEXT NOT NULL DEFAULT '',
                    architecture_decisions TEXT NOT NULL DEFAULT '[]',
                    context_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoint_goal
                ON project_checkpoints(goal_id, created_at DESC)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_journal (
                    id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    alternatives TEXT NOT NULL DEFAULT '[]',
                    rationale TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decision_goal
                ON decision_journal(goal_id, created_at DESC)
            """)
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Checkpoints ──────────────────────────────────────────

    def save_checkpoint(self, goal_id: str,
                        task_graph: TaskGraph | None = None,
                        project_path: str = "",
                        context_summary: str = "") -> Checkpoint:
        """Save a full project checkpoint. Call after each significant milestone."""
        cp_id = str(uuid.uuid4())
        now = self._now()

        goal = self.goals.get(goal_id) if self.goals else None
        goal_data = goal.to_dict() if goal else {}

        graph_data = task_graph.to_dict() if task_graph else {}

        decisions = self.get_decisions(goal_id)

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO project_checkpoints
                   (id, goal_id, goal_data, task_graph_data, project_path,
                    architecture_decisions, context_summary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (cp_id, goal_id, json.dumps(goal_data, default=str),
                 json.dumps(graph_data, default=str), project_path,
                 json.dumps(decisions, default=str), context_summary, now),
            )
            conn.commit()
            conn.close()

        logger.info("[ProjectPersistence] checkpoint %s for goal %s", cp_id[:8], goal_id[:8])
        return Checkpoint(
            id=cp_id, goal_id=goal_id, goal_data=goal_data,
            task_graph_data=graph_data, project_path=project_path,
            architecture_decisions=decisions, context_summary=context_summary,
            created_at=now,
        )

    def load_latest_checkpoint(self, goal_id: str) -> Checkpoint | None:
        """Load the most recent checkpoint for a goal (for resume)."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT * FROM project_checkpoints
                   WHERE goal_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (goal_id,),
            ).fetchone()
            conn.close()

        if not row:
            return None

        return Checkpoint(
            id=row["id"],
            goal_id=row["goal_id"],
            goal_data=json.loads(row["goal_data"]),
            task_graph_data=json.loads(row["task_graph_data"]),
            project_path=row["project_path"],
            architecture_decisions=json.loads(row["architecture_decisions"]),
            context_summary=row["context_summary"],
            created_at=row["created_at"],
        )

    def load_checkpoint_by_id(self, cp_id: str) -> Checkpoint | None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM project_checkpoints WHERE id = ?", (cp_id,)
            ).fetchone()
            conn.close()
        if not row:
            return None
        return Checkpoint(
            id=row["id"], goal_id=row["goal_id"],
            goal_data=json.loads(row["goal_data"]),
            task_graph_data=json.loads(row["task_graph_data"]),
            project_path=row["project_path"],
            architecture_decisions=json.loads(row["architecture_decisions"]),
            context_summary=row["context_summary"],
            created_at=row["created_at"],
        )

    def list_checkpoints(self, goal_id: str, limit: int = 10) -> list[Checkpoint]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM project_checkpoints
                   WHERE goal_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (goal_id, limit),
            ).fetchall()
            conn.close()
        result = []
        for r in rows:
            result.append(Checkpoint(
                id=r["id"], goal_id=r["goal_id"],
                goal_data=json.loads(r["goal_data"]),
                task_graph_data=json.loads(r["task_graph_data"]),
                project_path=r["project_path"],
                architecture_decisions=json.loads(r["architecture_decisions"]),
                context_summary=r["context_summary"],
                created_at=r["created_at"],
            ))
        return result

    def resume_context(self, goal_id: str) -> str:
        """Generate a context string for LLM re-hydration after resume.

        Includes: goal state, last checkpoint summary, recent decisions.
        Useful for Day 5 → resume automatically.
        """
        cp = self.load_latest_checkpoint(goal_id)
        if not cp:
            return ""

        goal = self.goals.get(goal_id) if self.goals else None

        lines = ["=== PROJECT RESUME ==="]
        if goal:
            lines.append(f"Goal: {goal.objective}")
            lines.append(f"Status: {goal.status.value}")
            lines.append(f"Progress: {goal.progress:.0%}")
            if goal.blockers:
                lines.append(f"Blockers: {goal.blockers}")

        lines.append(f"\nLast checkpoint: {cp.created_at}")
        if cp.context_summary:
            lines.append(f"\nContext:\n{cp.context_summary[:500]}")

        if cp.architecture_decisions:
            lines.append(f"\nArchitecture decisions ({len(cp.architecture_decisions)}):")
            for d in cp.architecture_decisions[:5]:
                lines.append(f"  - {d.get('title', '?')}: {d.get('decision', '')[:100]}")

        return "\n".join(lines)

    # ── Decision Journal ─────────────────────────────────────

    def record_decision(self, goal_id: str, title: str, decision: str,
                        alternatives: list[str] | None = None,
                        rationale: str = "",
                        outcome: str = "") -> str:
        """Record an architecture or design decision."""
        dec_id = str(uuid.uuid4())
        now = self._now()

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO decision_journal
                   (id, goal_id, title, decision, alternatives, rationale, outcome, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (dec_id, goal_id, title, decision,
                 json.dumps(alternatives or []), rationale, outcome, now),
            )
            conn.commit()
            conn.close()

        logger.info("[ProjectPersistence] decision recorded: %s", title)
        return dec_id

    def get_decisions(self, goal_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_journal
                   WHERE goal_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (goal_id, limit),
            ).fetchall()
            conn.close()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "goal_id": r["goal_id"],
                "title": r["title"],
                "decision": r["decision"],
                "alternatives": json.loads(r["alternatives"]),
                "rationale": r["rationale"],
                "outcome": r["outcome"],
                "created_at": r["created_at"],
            })
        return result

    def get_all_checkpoints_count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            count = conn.execute("SELECT COUNT(*) FROM project_checkpoints").fetchone()[0]
            conn.close()
        return count

    def get_all_decisions_count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            count = conn.execute("SELECT COUNT(*) FROM decision_journal").fetchone()[0]
            conn.close()
        return count
