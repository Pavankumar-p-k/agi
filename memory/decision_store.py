from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from memory.similarity import get_text_similarity

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _get_db_path() -> str:
    os.makedirs(_DB_DIR, exist_ok=True)
    return os.path.join(_DB_DIR, "memory.db")


class DecisionStore:
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
                CREATE TABLE IF NOT EXISTS decision_memories (
                    id TEXT PRIMARY KEY,
                    context TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    alternatives TEXT NOT NULL DEFAULT '[]',
                    outcome TEXT NOT NULL DEFAULT '',
                    lesson TEXT NOT NULL DEFAULT '',
                    success INTEGER NOT NULL DEFAULT 0,
                    importance REAL NOT NULL DEFAULT 0.0,
                    tags TEXT NOT NULL DEFAULT '[]',
                    user_id TEXT NOT NULL DEFAULT 'default',
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            for col, idx_name in [
                ("importance DESC", "idx_decision_importance"),
                ("success", "idx_decision_success"),
                ("created_at DESC", "idx_decision_created"),
                ("user_id", "idx_decision_user"),
            ]:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON decision_memories({col})"
                )
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _compute_importance(self, success: bool, outcome: str) -> float:
        score = 0.3
        if success:
            score += 0.2
        else:
            score += 0.4
        if len(outcome) > 100:
            score += 0.1
        return round(min(1.0, score), 2)

    def store(self, context: str, decision: str,
              alternatives: list[str] | None = None,
              outcome: str = "", lesson: str = "",
              success: bool = False,
              tags: list[str] | None = None,
              user_id: str = "default") -> str:
        entry_id = str(uuid.uuid4())
        now = self._now()
        imp = self._compute_importance(success, outcome)
        alt_list = alternatives or []
        tag_list = tags or []

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO decision_memories
                   (id, context, decision, alternatives, outcome, lesson,
                    success, importance, tags, user_id, created_at, accessed_at, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (entry_id, context, decision,
                 json.dumps(alt_list), outcome, lesson,
                 1 if success else 0, imp,
                 json.dumps(tag_list), user_id, now, now),
            )
            conn.commit()
            conn.close()

        logger.debug("[DecisionStore] stored decision %s: %s success=%s", entry_id, decision[:80], success)
        return entry_id

    def retrieve_similar(self, query_context: str, top_k: int = 5,
                         user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_memories
                   WHERE user_id = ?
                   ORDER BY importance DESC, access_count DESC
                   LIMIT ?""",
                (user_id, top_k * 3),
            ).fetchall()
            conn.close()

        candidates = [dict(r) for r in rows]
        for c in candidates:
            c["_similarity"] = get_text_similarity(query_context, c["context"])
            c["alternatives"] = json.loads(c.get("alternatives", "[]"))
            c["tags"] = json.loads(c.get("tags", "[]"))

        candidates.sort(key=lambda x: x["_similarity"], reverse=True)

        for c in candidates:
            if not c["success"] and c.get("lesson"):
                c["_similarity"] = min(1.0, c["_similarity"] + 0.15)

        candidates.sort(key=lambda x: x["_similarity"], reverse=True)
        return candidates[:top_k]

    def get_failures(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_memories
                   WHERE user_id = ? AND success = 0 AND lesson != ''
                   ORDER BY importance DESC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["alternatives"] = json.loads(d.get("alternatives", "[]"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_lessons(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_memories
                   WHERE user_id = ? AND lesson != ''
                   ORDER BY importance DESC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["alternatives"] = json.loads(d.get("alternatives", "[]"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_recent(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM decision_memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["alternatives"] = json.loads(d.get("alternatives", "[]"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def clear(self, user_id: str = "default") -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM decision_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.execute("DELETE FROM decision_memories WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        logger.info("[DecisionStore] cleared %d decisions for user %s", row[0], user_id)
        return row[0]

    def count(self, user_id: str = "default") -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM decision_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.close()
        return row[0]
