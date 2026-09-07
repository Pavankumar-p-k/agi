from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _get_db_path() -> str:
    os.makedirs(_DB_DIR, exist_ok=True)
    return os.path.join(_DB_DIR, "memory.db")


class TaskStore:
    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _get_db_path()
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
                    user_id TEXT NOT NULL DEFAULT 'default',
                    created_at TEXT NOT NULL
                )
            """)
            for col, idx_name in [
                ("task_id", "idx_task_task_id"),
                ("action_name", "idx_task_action"),
                ("success", "idx_task_success"),
                ("created_at DESC", "idx_task_created"),
                ("user_id", "idx_task_user"),
            ]:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON task_memories({col})"
                )
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def store(self, action_name: str, action_params: dict | None = None,
              observation: str = "", success: bool = False,
              duration_ms: float = 0.0, task_id: str = "",
              context: dict | None = None,
              tags: list[str] | None = None,
              user_id: str = "default") -> str:
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
                    duration_ms, context, tags, user_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, task_id, action_name,
                 json.dumps(params, default=str),
                 observation, 1 if success else 0,
                 duration_ms,
                 json.dumps(ctx, default=str),
                 json.dumps(tag_list), user_id, now),
            )
            conn.commit()
            conn.close()

        logger.debug("[TaskStore] stored trace %s: %s success=%s", entry_id, action_name, success)
        return entry_id

    def get_task_traces(self, task_id: str, user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_memories WHERE user_id = ? AND task_id = ? ORDER BY created_at ASC",
                (user_id, task_id),
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

    def get_action_patterns(self, action_name: str, min_samples: int = 3,
                            user_id: str = "default") -> dict:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_memories WHERE user_id = ? AND action_name = ? ORDER BY created_at DESC LIMIT 100",
                (user_id, action_name),
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

    def get_recent(self, limit: int = 50, user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
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

    def get_success_rate(self, action_name: str | None = None,
                         user_id: str = "default") -> float:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            if action_name:
                total = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE user_id = ? AND action_name = ?",
                    (user_id, action_name),
                ).fetchone()[0]
                successes = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE user_id = ? AND action_name = ? AND success = 1",
                    (user_id, action_name),
                ).fetchone()[0]
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE user_id = ?",
                    (user_id,),
                ).fetchone()[0]
                successes = conn.execute(
                    "SELECT COUNT(*) FROM task_memories WHERE user_id = ? AND success = 1",
                    (user_id,),
                ).fetchone()[0]
            conn.close()

        if total == 0:
            return 0.0
        return successes / total

    def clear(self, user_id: str = "default") -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM task_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.execute("DELETE FROM task_memories WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        logger.info("[TaskStore] cleared %d traces for user %s", row[0], user_id)
        return row[0]

    def count(self, user_id: str = "default") -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM task_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.close()
        return row[0]
