"""Persistent store for scheduler queue state + user-facing schedules.

Lives in the same `data/workflow.db` as ActivityStore so activities
and scheduler metadata stay consistent without cross-database joins.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.scheduler.models import ScheduleModel, ScheduledActivity
from core.storage import SYSTEM_DB

logger = logging.getLogger(__name__)

_DEFAULT_DB = SYSTEM_DB

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scheduled_activities (
    activity_id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    goal TEXT NOT NULL DEFAULT '',
    node_type TEXT NOT NULL DEFAULT 'goal',
    depends_on TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    activity_id TEXT,
    workflow_id TEXT,
    cron TEXT,
    interval_seconds INTEGER,
    next_run_at TEXT,
    last_run_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
"""
_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_scheduled_status ON scheduled_activities(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_priority ON scheduled_activities(priority);
CREATE INDEX IF NOT EXISTS idx_schedules_status ON schedules(status);
"""


class SchedulerStore:
    """SQLite-backed persistence for scheduler queue state.

    Thread-safe. Each CRUD method opens its own connection.
    Tables are created lazily on first use.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(_TABLE_SQL + _INDEX_SQL)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add(self, act: ScheduledActivity) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO scheduled_activities
                   (activity_id, priority, score, status, goal, node_type,
                    depends_on, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    act.activity_id,
                    act.priority,
                    act.score,
                    act.status,
                    act.goal,
                    act.node_type,
                    json.dumps(act.depends_on),
                    json.dumps(act.metadata),
                    act.created_at.isoformat() if act.created_at else now,
                    now,
                ),
            )

    def get(self, activity_id: str) -> ScheduledActivity | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM scheduled_activities WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()
        return self._row_to_activity(row) if row else None

    def list_all(self) -> list[ScheduledActivity]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_activities ORDER BY priority DESC, created_at ASC"
            ).fetchall()
        return [self._row_to_activity(r) for r in rows]

    def list_by_status(self, status: str) -> list[ScheduledActivity]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_activities WHERE status = ? ORDER BY priority DESC, created_at ASC",
                (status,),
            ).fetchall()
        return [self._row_to_activity(r) for r in rows]

    def update_status(self, activity_id: str, status: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE scheduled_activities SET status = ?, updated_at = ? WHERE activity_id = ?",
                (status, now, activity_id),
            )

    def update_priority(self, activity_id: str, priority: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE scheduled_activities SET priority = ?, updated_at = ? WHERE activity_id = ?",
                (priority, now, activity_id),
            )

    def update_metadata(self, activity_id: str, key: str, value: Any) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT metadata FROM scheduled_activities WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()
            if not row:
                return
            meta = json.loads(row[0])
            meta[key] = value
            conn.execute(
                "UPDATE scheduled_activities SET metadata = ?, updated_at = ? WHERE activity_id = ?",
                (json.dumps(meta), now, activity_id),
            )

    def delete(self, activity_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM scheduled_activities WHERE activity_id = ?",
                (activity_id,),
            )

    def count(self) -> int:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM scheduled_activities").fetchone()
        return row[0] if row else 0

    # ── Schedule CRUD ─────────────────────────────────────────────────────────

    def add_schedule(self, sched: ScheduleModel) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO schedules
                   (id, name, activity_id, workflow_id, cron, interval_seconds,
                    next_run_at, last_run_at, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sched.id,
                    sched.name,
                    sched.activity_id,
                    sched.workflow_id,
                    sched.cron,
                    sched.interval_seconds,
                    sched.next_run_at.isoformat() if sched.next_run_at else None,
                    sched.last_run_at.isoformat() if sched.last_run_at else None,
                    sched.status,
                    sched.created_at.isoformat() if sched.created_at else now,
                ),
            )

    def get_schedule(self, schedule_id: str) -> ScheduleModel | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
        return self._row_to_schedule(row) if row else None

    def list_schedules(self, status: str | None = None) -> list[ScheduleModel]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM schedules ORDER BY created_at DESC"
                ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def update_schedule_status(self, schedule_id: str, status: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE schedules SET status = ? WHERE id = ?",
                (status, schedule_id),
            )

    def update_schedule_run_time(
        self, schedule_id: str, last_run_at: datetime, next_run_at: datetime | None = None
    ) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
                (
                    last_run_at.isoformat(),
                    next_run_at.isoformat() if next_run_at else None,
                    schedule_id,
                ),
            )

    def delete_schedule(self, schedule_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def list_by_metadata(self, key: str, value: str) -> list[ScheduledActivity]:
        """Find activities whose metadata contains the given key=value pair."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_activities ORDER BY created_at ASC"
            ).fetchall()
        result = []
        for r in rows:
            act = self._row_to_activity(r)
            if act.metadata.get(key) == value:
                result.append(act)
        return result

    def clear(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM scheduled_activities")

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> ScheduleModel:
        return ScheduleModel(
            id=row[0],
            name=row[1],
            activity_id=row[2],
            workflow_id=row[3],
            cron=row[4],
            interval_seconds=row[5],
            next_run_at=_parse_iso(row[6]),
            last_run_at=_parse_iso(row[7]),
            status=row[8],
            created_at=_parse_iso(row[9]),
        )

    @staticmethod
    def _row_to_activity(row: sqlite3.Row) -> ScheduledActivity:
        return ScheduledActivity(
            activity_id=row[0],
            priority=row[1],
            score=row[2],
            status=row[3],
            goal=row[4],
            node_type=row[5],
            depends_on=json.loads(row[6]),
            metadata=json.loads(row[7]),
            created_at=_parse_iso(row[8]),
        )


def _parse_iso(ts: str | None) -> datetime | None:
    if ts:
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            pass
    return None
