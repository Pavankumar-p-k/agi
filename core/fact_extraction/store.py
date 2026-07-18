import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.storage import MEMORY_DB
from .models import ExtractedFact


_DEFAULT_DB_PATH = Path(MEMORY_DB)


class BrowserFactStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or _DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._init_db()
        return self._conn

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS browser_facts (
                fact_id TEXT PRIMARY KEY,
                claim TEXT NOT NULL,
                claim_norm TEXT NOT NULL,
                entity TEXT,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                confidence REAL NOT NULL DEFAULT 0.5,
                tags TEXT NOT NULL DEFAULT '[]',
                attributes TEXT NOT NULL DEFAULT '{}',
                times_seen INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_browser_facts_entity
            ON browser_facts(entity)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_browser_facts_category
            ON browser_facts(category)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_browser_facts_confidence
            ON browser_facts(confidence)
        """)
        self._conn.commit()

    def store_facts(self, facts: list[ExtractedFact]):
        if not facts:
            return
        now = datetime.utcnow().isoformat(timespec="seconds")
        cursor = self.conn.cursor()
        for f in facts:
            c_norm = self._normalize(f.claim)
            existing = cursor.execute(
                "SELECT fact_id, times_seen FROM browser_facts WHERE claim_norm = ? AND source_url = ?",
                (c_norm, f.source_url),
            ).fetchone()
            if existing:
                cursor.execute(
                    "UPDATE browser_facts SET times_seen = ?, last_seen = ?, confidence = MAX(confidence, ?) WHERE fact_id = ?",
                    (existing["times_seen"] + 1, now, f.confidence, existing["fact_id"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO browser_facts (fact_id, claim, claim_norm, entity, source_url, source_type, category, confidence, tags, attributes, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f.fact_id,
                        f.claim,
                        c_norm,
                        f.entity,
                        f.source_url,
                        f.source_type,
                        f.category,
                        f.confidence,
                        json.dumps(f.tags),
                        json.dumps(f.attributes),
                        now,
                        now,
                    ),
                )
        self.conn.commit()

    def get_facts_by_entity(self, entity: str, min_confidence: float = 0.0) -> list[ExtractedFact]:
        rows = self.conn.execute(
            "SELECT * FROM browser_facts WHERE entity = ? AND confidence >= ? ORDER BY confidence DESC",
            (entity, min_confidence),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def get_facts_by_category(self, category: str, limit: int = 50) -> list[ExtractedFact]:
        rows = self.conn.execute(
            "SELECT * FROM browser_facts WHERE category = ? ORDER BY confidence DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def get_all_facts(self, limit: int = 200) -> list[ExtractedFact]:
        rows = self.conn.execute(
            "SELECT * FROM browser_facts ORDER BY confidence DESC, times_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def search_facts(self, query: str, limit: int = 20) -> list[ExtractedFact]:
        q = f"%{query}%"
        rows = self.conn.execute(
            "SELECT * FROM browser_facts WHERE claim LIKE ? OR entity LIKE ? ORDER BY confidence DESC LIMIT ?",
            (q, q, limit),
        ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def delete_fact(self, fact_id: str):
        self.conn.execute("DELETE FROM browser_facts WHERE fact_id = ?", (fact_id,))
        self.conn.commit()

    def fact_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM browser_facts").fetchone()
        return row["cnt"] if row else 0

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _normalize(text: str) -> str:
        import re
        t = re.sub(r"\s+", " ", text).strip().lower()
        t = re.sub(r"[^a-z0-9\s]", "", t)
        return t

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> ExtractedFact:
        return ExtractedFact(
            fact_id=row["fact_id"],
            entity=row["entity"],
            claim=row["claim"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            category=row["category"],
            confidence=row["confidence"],
            tags=json.loads(row["tags"]),
            attributes=json.loads(row["attributes"]),
            extracted_at=row["last_seen"],
        )
