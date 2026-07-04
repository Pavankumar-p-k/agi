from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from core.memory import get_text_similarity

from .base import MemoryProvider

logger = logging.getLogger(__name__)


class DecisionMemory(MemoryProvider):
    """Decision memory — stores every decision made, its outcome, and the lesson learned.

    This is the core of self-reflection: after every task, the system records
    what worked, what failed, and how to improve. Future decisions can retrieve
    similar past decisions to avoid repeating mistakes.
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
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decision_importance
                ON decision_memories(importance DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decision_success
                ON decision_memories(success)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decision_created
                ON decision_memories(created_at DESC)
            """)
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
              tags: list[str] | None = None) -> str:
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
                    success, importance, tags, created_at, accessed_at, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (entry_id, context, decision,
                 json.dumps(alt_list), outcome, lesson,
                 1 if success else 0, imp,
                 json.dumps(tag_list), now, now),
            )
            conn.commit()
            conn.close()

        logger.debug("[DecisionMemory] stored decision %s: %s success=%s", entry_id, decision[:80], success)
        return entry_id

    def retrieve_similar(self, query_context: str, top_k: int = 5) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_memories
                   ORDER BY importance DESC, access_count DESC
                   LIMIT ?""",
                (top_k * 3,),
            ).fetchall()
            conn.close()

        candidates = [dict(r) for r in rows]
        for c in candidates:
            c["_similarity"] = get_text_similarity(query_context, c["context"])
            c["alternatives"] = json.loads(c.get("alternatives", "[]"))
            c["tags"] = json.loads(c.get("tags", "[]"))

        candidates.sort(key=lambda x: x["_similarity"], reverse=True)

        # Boost failure lessons in retrieval — they're more valuable
        for c in candidates:
            if not c["success"] and c.get("lesson"):
                c["_similarity"] = min(1.0, c["_similarity"] + 0.15)

        candidates.sort(key=lambda x: x["_similarity"], reverse=True)
        return candidates[:top_k]

    def get_failures(self, limit: int = 20) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_memories
                   WHERE success = 0 AND lesson != ''
                   ORDER BY importance DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["alternatives"] = json.loads(d.get("alternatives", "[]"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_lessons(self, limit: int = 20) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM decision_memories
                   WHERE lesson != ''
                   ORDER BY importance DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()

        result = []
        for r in rows:
            d = dict(r)
            d["alternatives"] = json.loads(d.get("alternatives", "[]"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM decision_memories ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["alternatives"] = json.loads(d.get("alternatives", "[]"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def clear(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM decision_memories").fetchone()
            conn.execute("DELETE FROM decision_memories")
            conn.commit()
            conn.close()
        logger.info("[DecisionMemory] cleared %d decisions", row[0])
        return row[0]

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM decision_memories").fetchone()
            conn.close()
        return row[0]
