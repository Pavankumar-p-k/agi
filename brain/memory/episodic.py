from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from core.memory import get_text_similarity

from .base import MemoryProvider

logger = logging.getLogger(__name__)


class EpisodicMemory(MemoryProvider):
    """Episodic memory — stores task episodes as sequences of actions with context and outcomes.

    Each episode captures a complete goal-driven interaction: what was attempted,
    what actions were taken, what the result was. Supports retrieval by similarity,
    importance scoring, and automatic summarization of old episodes.
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
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id TEXT PRIMARY KEY,
                    episode_type TEXT NOT NULL DEFAULT 'task',
                    goal TEXT NOT NULL,
                    actions TEXT NOT NULL DEFAULT '[]',
                    context TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '{}',
                    tags TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_type
                ON episodic_memories(episode_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_importance
                ON episodic_memories(importance DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_episodic_created
                ON episodic_memories(created_at DESC)
            """)
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _importance_score(self, result: dict, actions: list) -> float:
        """Heuristic importance: outcome significance + action complexity + recency."""
        score = 0.3
        success = result.get("success", False)
        if success:
            score += 0.3
        error = result.get("error")
        if error:
            score += 0.4
        score += min(0.3, len(actions) * 0.05)
        return round(min(1.0, score), 2)

    def store(self, goal: str, actions: list[dict], context: dict | None = None,
              result: dict | None = None, episode_type: str = "task",
              tags: list[str] | None = None) -> str:
        entry_id = str(uuid.uuid4())
        now = self._now()
        result_data = result or {}
        ctx_data = context or {}
        tag_list = tags or []
        imp = self._importance_score(result_data, actions)

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO episodic_memories
                   (id, episode_type, goal, actions, context, result, tags, importance,
                    created_at, accessed_at, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (entry_id, episode_type, goal,
                 json.dumps(actions, default=str),
                 json.dumps(ctx_data, default=str),
                 json.dumps(result_data, default=str),
                 json.dumps(tag_list),
                 imp, now, now),
            )
            conn.commit()
            conn.close()

        logger.debug("[EpisodicMemory] stored episode %s: goal=%s", entry_id, goal[:80])
        return entry_id

    def retrieve(self, query: str, top_k: int = 5,
                 min_importance: float = 0.0) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM episodic_memories
                   WHERE importance >= ?
                   ORDER BY access_count DESC, importance DESC
                   LIMIT ?""",
                (min_importance, top_k * 3),
            ).fetchall()
            conn.close()

        candidates = [dict(r) for r in rows]
        for c in candidates:
            c["_similarity"] = get_text_similarity(query, c["goal"])
            c["actions"] = json.loads(c.get("actions", "[]"))
            c["context"] = json.loads(c.get("context", "{}"))
            c["result"] = json.loads(c.get("result", "{}"))
            c["tags"] = json.loads(c.get("tags", "[]"))

        candidates.sort(key=lambda x: x["_similarity"], reverse=True)
        return candidates[:top_k]

    def get_recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM episodic_memories
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()

        results = []
        for r in rows:
            d = dict(r)
            d["actions"] = json.loads(d.get("actions", "[]"))
            d["context"] = json.loads(d.get("context", "{}"))
            d["result"] = json.loads(d.get("result", "{}"))
            d["tags"] = json.loads(d.get("tags", "[]"))
            results.append(d)
        return results

    def update_result(self, episode_id: str, result: dict):
        now = self._now()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE episodic_memories SET result = ?, accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                (json.dumps(result, default=str), now, episode_id),
            )
            conn.commit()
            conn.close()

    def summarize_old(self, before_days: int = 30) -> int:
        cutoff = (datetime.now(timezone.utc).timestamp() - before_days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT id, goal, result FROM episodic_memories WHERE created_at < ? AND episode_type != 'summary'",
                (cutoff_iso,),
            ).fetchall()
            if rows:
                summary_text = "; ".join(
                    f"{r[1][:60]}: {json.loads(r[2]).get('success', 'unknown')}"
                    for r in rows
                )
                summary_id = str(uuid.uuid4())
                now = self._now()
                conn.execute(
                    """INSERT INTO episodic_memories
                       (id, episode_type, goal, actions, context, result, tags, importance,
                        created_at, accessed_at, access_count)
                       VALUES (?, 'summary', ?, '[]', '{}', ?, '[\"summary\"]', 0.1, ?, ?, 0)""",
                    (summary_id, f"Summary of {len(rows)} episodes: {summary_text[:200]}",
                     json.dumps({"summarized_count": len(rows), "original_ids": [r[0] for r in rows]}),
                     now, now),
                )
                conn.execute("DELETE FROM episodic_memories WHERE id IN ({})".format(
                    ",".join("?" * len(rows))),
                    [r[0] for r in rows])
            conn.commit()
            conn.close()
        logger.info("[EpisodicMemory] summarized %d old episodes", len(rows))
        return len(rows)

    def clear(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM episodic_memories").fetchone()
            conn.execute("DELETE FROM episodic_memories")
            conn.commit()
            conn.close()
        logger.info("[EpisodicMemory] cleared %d episodes", row[0])
        return row[0]

    def maintenance(self) -> int:
        return self.summarize_old()

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM episodic_memories").fetchone()
            conn.close()
        return row[0]
