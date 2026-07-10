"""FactStore — SQLite-backed persistent fact storage.

Same pattern as ActivityStore. Lives in the same database
(data/workflow.db) for transactional consistency.
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

from core.research.models import Fact
from core.storage import SYSTEM_DB

logger = logging.getLogger(__name__)

_DEFAULT_DB = SYSTEM_DB


class FactStore:
    """Persistent storage for extracted facts.

    Thin CRUD layer. Facts are indexed by source_url, activity_id,
    category, and tags for fast lookup.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS research_facts (
                    fact_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    category TEXT NOT NULL DEFAULT 'general',
                    tags_json TEXT DEFAULT '[]',
                    timestamp TEXT NOT NULL,
                    activity_id TEXT,
                    node_id TEXT,
                    metadata_json TEXT DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_facts_source
                    ON research_facts(source_url);
                CREATE INDEX IF NOT EXISTS idx_facts_activity
                    ON research_facts(activity_id);
                CREATE INDEX IF NOT EXISTS idx_facts_category
                    ON research_facts(category);
            """)

    def insert_fact(self, fact: Fact) -> Fact:
        fact.timestamp = fact.timestamp or datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO research_facts
                   (fact_id, source_url, claim, confidence, category,
                    tags_json, timestamp, activity_id, node_id, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact.fact_id, fact.source_url, fact.claim, fact.confidence,
                    fact.category, json.dumps(fact.tags),
                    fact.timestamp.isoformat() if fact.timestamp else None,
                    fact.activity_id, fact.node_id,
                    json.dumps(fact.metadata),
                ),
            )
        return fact

    def get_fact(self, fact_id: str) -> Fact | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM research_facts WHERE fact_id=?", (fact_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_fact(row)

    def search_facts(self, query: str, limit: int = 20) -> list[Fact]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM research_facts
                   WHERE claim LIKE ?
                   ORDER BY confidence DESC, timestamp DESC
                   LIMIT ?""",
                (f"%{query}%", limit),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def get_facts_by_activity(self, activity_id: str) -> list[Fact]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM research_facts WHERE activity_id=? ORDER BY timestamp DESC",
                (activity_id,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def get_facts_by_source(self, source_url: str) -> list[Fact]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM research_facts WHERE source_url=? ORDER BY confidence DESC",
                (source_url,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def get_facts_by_category(self, category: str, limit: int = 50) -> list[Fact]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM research_facts WHERE category=? ORDER BY timestamp DESC LIMIT ?",
                (category, limit),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def get_all_facts(self, limit: int = 100) -> list[Fact]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM research_facts ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_fact(r) for r in rows]

    def delete_fact(self, fact_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM research_facts WHERE fact_id=?", (fact_id,))

    def delete_facts_by_activity(self, activity_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM research_facts WHERE activity_id=?", (activity_id,)
            )

    def count_facts(self) -> int:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM research_facts").fetchone()
            return row[0] if row else 0

    def count_by_source(self) -> dict[str, int]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT source_url, COUNT(*) as cnt FROM research_facts GROUP BY source_url ORDER BY cnt DESC"
            ).fetchall()
            return {r["source_url"]: r["cnt"] for r in rows}

    def count_by_category(self) -> dict[str, int]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM research_facts GROUP BY category ORDER BY cnt DESC"
            ).fetchall()
            return {r["category"]: r["cnt"] for r in rows}


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        fact_id=row["fact_id"],
        source_url=row["source_url"],
        claim=row["claim"],
        confidence=row["confidence"],
        category=row["category"],
        tags=json.loads(row["tags_json"]),
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
        activity_id=row["activity_id"],
        node_id=row["node_id"],
        metadata=json.loads(row["metadata_json"]),
    )
