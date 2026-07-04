from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .base import MemoryProvider

logger = logging.getLogger(__name__)


class TaskMemory(MemoryProvider):
    """Task memory — stores execution traces: every action attempted, its observation, and success.

    Used for learning which action sequences tend to succeed in which contexts.
    Supports pattern extraction over similar tasks.
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
                CREATE TABLE IF NOT EXISTS task_memories (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL DEFAULT '',
                    action_name TEXT NOT NULL,
                    action_params TEXT NOT NULL DEFAULT '{}',
                    observation TEXT NOT NULL DEFAULT '',
                    success INTEGER NOT NULL DEFAULT 0,
                    duration_ms REAL NOT NULL DEFAULT 0.0,
                    context TEXT NOT NULL DEFAULT '{}',
                    tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_task_id
                ON task_memories(task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_action
                ON task_memories(action_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_success
                ON task_memories(success)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_created
                ON task_memories(created_at DESC)
            """)
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def store(self, action_name: str, action_params: dict | None = None,
              observation: str = "", success: bool = False,
              duration_ms: float = 0.0, task_id: str = "",
              context: dict | None = None,
              tags: list[str] | None = None) -> str:
        entry_id = str(uuid.uuid4())
        now = self._now()
        params = action_params or {}
        ctx = context or {}
        tag_list = tags or []

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO task_memories
                   (id, task_id, action_name, action_params, observation, success,
                    duration_ms, context, tags, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, task_id, action_name,
                 json.dumps(params, default=str),
                 observation, 1 if success else 0,
                 duration_ms,
                 json.dumps(ctx, default=str),
                 json.dumps(tag_list), now),
            )
            conn.commit()
            conn.close()

        logger.debug("[TaskMemory] stored trace %s: %s success=%s", entry_id, action_name, success)
        return entry_id

    def get_task_traces(self, task_id: str) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_memories WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["action_params"] = json.loads(d.get("action_params", "{}"))
            d["context"] = json.loads(d.get("context", "{}"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_action_patterns(self, action_name: str, min_samples: int = 3) -> dict:
        """Extract success/failure patterns for a given action type."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_memories WHERE action_name = ? ORDER BY created_at DESC LIMIT 100",
                (action_name,),
            ).fetchall()
            conn.close()

        if len(rows) < min_samples:
            return {"action": action_name, "samples": len(rows), "pattern": "insufficient_data"}

        successes = sum(1 for r in rows if r["success"])
        total = len(rows)
        success_rate = successes / total

        return {
            "action": action_name,
            "samples": total,
            "success_rate": round(success_rate, 2),
            "pattern": "reliable" if success_rate >= 0.8 else "unreliable" if success_rate >= 0.5 else "fragile",
        }

    def get_recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_memories ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["action_params"] = json.loads(d.get("action_params", "{}"))
            d["context"] = json.loads(d.get("context", "{}"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_success_rate(self, action_name: str | None = None) -> float:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            if action_name:
                total = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE action_name = ?",
                    (action_name,),
                ).fetchone()[0]
                successes = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE action_name = ? AND success = 1",
                    (action_name,),
                ).fetchone()[0]
            else:
                total = conn.execute("SELECT COUNT(*) FROM task_memories").fetchone()[0]
                successes = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE success = 1"
                ).fetchone()[0]
            conn.close()

        if total == 0:
            return 0.0
        return successes / total

    def clear(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM task_memories").fetchone()
            conn.execute("DELETE FROM task_memories")
            conn.commit()
            conn.close()
        logger.info("[TaskMemory] cleared %d traces", row[0])
        return row[0]

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM task_memories").fetchone()
            conn.close()
        return row[0]
