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


class EpisodicStore:
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
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id TEXT PRIMARY KEY,
                    episode_type TEXT NOT NULL DEFAULT 'task',
                    goal TEXT NOT NULL,
                    actions TEXT NOT NULL DEFAULT '[]',
                    context TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '{}',
                    tags TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.0,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            for col, idx_name in [
                ("episode_type", "idx_episodic_type"),
                ("importance DESC", "idx_episodic_importance"),
                ("created_at DESC", "idx_episodic_created"),
                ("user_id", "idx_episodic_user"),
            ]:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON episodic_memories({col})"
                )
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _importance_score(self, result: dict, actions: list) -> float:
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
              tags: list[str] | None = None,
              user_id: str = "default") -> str:
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
                    user_id, created_at, accessed_at, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (entry_id, episode_type, goal,
                 json.dumps(actions, default=str),
                 json.dumps(ctx_data, default=str),
                 json.dumps(result_data, default=str),
                 json.dumps(tag_list),
                 imp, user_id, now, now),
            )
            conn.commit()
            conn.close()

        logger.debug("[EpisodicStore] stored episode %s: goal=%s", entry_id, goal[:80])
        return entry_id

    def retrieve(self, query: str, top_k: int = 5,
                 min_importance: float = 0.0,
                 user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM episodic_memories
                   WHERE user_id = ? AND importance >= ?
                   ORDER BY access_count DESC, importance DESC
                   LIMIT ?""",
                (user_id, min_importance, top_k * 3),
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

    def get_recent(self, limit: int = 20, user_id: str = "default") -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM episodic_memories
                   WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
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

    def summarize_old(self, before_days: int = 30, user_id: str = "default") -> int:
        cutoff = (datetime.now(timezone.utc).timestamp() - before_days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT id, goal, result FROM episodic_memories WHERE user_id = ? AND created_at < ? AND episode_type != 'summary'",
                (user_id, cutoff_iso),
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
                        user_id, created_at, accessed_at, access_count)
                       VALUES (?, 'summary', ?, '[]', '{}', ?, '[\"summary\"]', 0.1, ?, ?, ?, 0)""",
                    (summary_id, f"Summary of {len(rows)} episodes: {summary_text[:200]}",
                     json.dumps({"summarized_count": len(rows), "original_ids": [r[0] for r in rows]}),
                     user_id, now, now),
                )
                conn.execute("DELETE FROM episodic_memories WHERE id IN ({})".format(
                    ",".join("?" * len(rows))),
                    [r[0] for r in rows])
            conn.commit()
            conn.close()
        logger.info("[EpisodicStore] summarized %d old episodes", len(rows))
        return len(rows)

    def clear(self, user_id: str = "default") -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.execute("DELETE FROM episodic_memories WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
        logger.info("[EpisodicStore] cleared %d episodes for user %s", row[0], user_id)
        return row[0]

    def count(self, user_id: str = "default") -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.close()
        return row[0]
