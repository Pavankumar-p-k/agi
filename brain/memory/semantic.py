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


class SemanticMemory(MemoryProvider):
    """Semantic memory — stores facts, knowledge, and concepts extracted from experience.

    Facts are stored with confidence scores and tracked by access patterns.
    Supports importance-based retention, deduplication, and similarity retrieval.
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
                CREATE TABLE IF NOT EXISTS semantic_memories (
                    id TEXT PRIMARY KEY,
                    fact TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    source TEXT NOT NULL DEFAULT 'inference',
                    tags TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    accessed_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_category
                ON semantic_memories(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_importance
                ON semantic_memories(importance DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_confidence
                ON semantic_memories(confidence DESC)
            """)
            conn.commit()
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _compute_importance(self, confidence: float, source: str) -> float:
        base = confidence * 0.5
        if source in {"verification", "observation", "user"}:
            base += 0.3
        elif source == "inference":
            base += 0.1
        return round(min(1.0, base), 2)

    def store(self, fact: str, category: str = "general",
              confidence: float = 1.0, source: str = "inference",
              tags: list[str] | None = None) -> str:
        entry_id = str(uuid.uuid4())
        now = self._now()
        imp = self._compute_importance(confidence, source)
        tag_list = tags or []

        # Deduplicate: if the same fact exists, update it
        existing = self._find_exact(fact)
        if existing:
            self._update_fact(existing["id"], fact, confidence, source, tag_list)
            return existing["id"]

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO semantic_memories
                   (id, fact, category, confidence, source, tags, importance,
                    created_at, accessed_at, access_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (entry_id, fact, category, confidence, source,
                 json.dumps(tag_list), imp, now, now),
            )
            conn.commit()
            conn.close()

        logger.debug("[SemanticMemory] stored fact %s: %s", entry_id, fact[:100])
        return entry_id

    def _find_exact(self, fact: str) -> dict | None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM semantic_memories WHERE fact = ?", (fact,)
            ).fetchone()
            conn.close()
        return dict(row) if row else None

    def _update_fact(self, fact_id: str, fact: str, confidence: float,
                     source: str, tags: list[str]):
        now = self._now()
        imp = self._compute_importance(confidence, source)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """UPDATE semantic_memories
                   SET confidence = ?, source = ?, tags = ?, importance = ?,
                       accessed_at = ?, access_count = access_count + 1
                   WHERE id = ?""",
                (confidence, source, json.dumps(tags), imp, now, fact_id),
            )
            conn.commit()
            conn.close()

    def retrieve(self, query: str, top_k: int = 8,
                 min_confidence: float = 0.0,
                 categories: list[str] | None = None) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row

            if categories:
                placeholders = ",".join("?" * len(categories))
                rows = conn.execute(
                    f"""SELECT * FROM semantic_memories
                       WHERE confidence >= ? AND category IN ({placeholders})
                       ORDER BY importance DESC, access_count DESC
                       LIMIT ?""",
                    [min_confidence] + categories + [top_k * 3],
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM semantic_memories
                       WHERE confidence >= ?
                       ORDER BY importance DESC, access_count DESC
                       LIMIT ?""",
                    (min_confidence, top_k * 3),
                ).fetchall()
            conn.close()

        candidates = [dict(r) for r in rows]
        for c in candidates:
            c["_similarity"] = get_text_similarity(query, c["fact"])
            c["tags"] = json.loads(c.get("tags", "[]"))

        candidates.sort(key=lambda x: x["_similarity"], reverse=True)
        return candidates[:top_k]

    def get_by_category(self, category: str, limit: int = 50) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM semantic_memories
                   WHERE category = ?
                   ORDER BY importance DESC LIMIT ?""",
                (category, limit),
            ).fetchall()
            conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def get_all_facts(self, limit: int = 200) -> list[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM semantic_memories
                   ORDER BY importance DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags", "[]"))
            result.append(d)
        return result

    def decay(self, factor: float = 0.95) -> int:
        """Reduce importance of old, rarely accessed facts (memory decay)."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE semantic_memories SET importance = importance * ? WHERE access_count < 2 AND importance > 0.1",
                (factor,),
            )
            affected = conn.execute(
                "SELECT changes()"
            ).fetchone()[0]
            conn.commit()
            conn.close()
        if affected:
            logger.debug("[SemanticMemory] applied decay to %d facts", affected)
        return affected

    def get_recent(self, limit: int = 20) -> list[dict]:
        return self.get_all_facts(limit)

    def clear(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM semantic_memories").fetchone()
            conn.execute("DELETE FROM semantic_memories")
            conn.commit()
            conn.close()
        logger.info("[SemanticMemory] cleared %d facts", row[0])
        return row[0]

    def maintenance(self) -> int:
        return self.decay()

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM semantic_memories").fetchone()
            conn.close()
        return row[0]
