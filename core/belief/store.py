"""BeliefStore — SQLite-backed persistence for belief quality data.

Tables:
  - source_profiles: per-source reliability tracking
  - accuracy_records: per-prediction accuracy tracking

Lives in the same database (data/workflow.db) as the activity graph,
knowledge store, and research facts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.belief.models import (
    AccuracyRecord,
    SourceProfile,
    SourceType,
)
from core.storage import SYSTEM_DB as UNIFIED_DB

logger = logging.getLogger(__name__)


class BeliefStore:
    """Persistent storage for belief quality data.

    Tables:
      - source_profiles: reliability tracking per source
      - accuracy_records: prediction accuracy tracking
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or UNIFIED_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS source_profiles (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL DEFAULT 'research_url',
                    reliability_score REAL NOT NULL DEFAULT 0.5,
                    domain_scores_json TEXT DEFAULT '{}',
                    total_references INTEGER NOT NULL DEFAULT 0,
                    correct_references INTEGER NOT NULL DEFAULT 0,
                    contradictory_references INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT
                );

                CREATE TABLE IF NOT EXISTS accuracy_records (
                    record_id TEXT PRIMARY KEY,
                    belief_id TEXT NOT NULL,
                    domain TEXT NOT NULL DEFAULT 'general',
                    category TEXT NOT NULL DEFAULT 'heuristic',
                    predicted_value REAL NOT NULL,
                    actual_value REAL NOT NULL,
                    error REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    source_id TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_accuracy_domain
                    ON accuracy_records(domain);
                CREATE INDEX IF NOT EXISTS idx_accuracy_category
                    ON accuracy_records(category);
                CREATE INDEX IF NOT EXISTS idx_accuracy_belief
                    ON accuracy_records(belief_id);
                CREATE INDEX IF NOT EXISTS idx_source_type
                    ON source_profiles(source_type);
            """)

    # ── SourceProfile CRUD ────────────────────────────────────────────

    def save_source_profile(self, profile: SourceProfile) -> SourceProfile:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO source_profiles
                   (source_id, source_type, reliability_score, domain_scores_json,
                    total_references, correct_references, contradictory_references,
                    first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile.source_id,
                    profile.source_type.value,
                    profile.reliability_score,
                    json.dumps(profile.domain_scores),
                    profile.total_references,
                    profile.correct_references,
                    profile.contradictory_references,
                    profile.first_seen.isoformat() if profile.first_seen else None,
                    profile.last_seen.isoformat() if profile.last_seen else None,
                ),
            )
        return profile

    def get_source_profile(self, source_id: str) -> SourceProfile | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM source_profiles WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_source_profile(row)

    def get_all_source_profiles(self) -> list[SourceProfile]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM source_profiles ORDER BY total_references DESC"
            ).fetchall()
            return [_row_to_source_profile(r) for r in rows]

    def delete_source_profile(self, source_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM source_profiles WHERE source_id=?",
                (source_id,),
            )

    def source_profile_count(self) -> int:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM source_profiles"
            ).fetchone()
            return row[0] if row else 0

    # ── AccuracyRecord CRUD ───────────────────────────────────────────

    def save_accuracy_record(self, record: AccuracyRecord) -> AccuracyRecord:
        ts = record.timestamp.isoformat() if record.timestamp else datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO accuracy_records
                   (record_id, belief_id, domain, category,
                    predicted_value, actual_value, error, timestamp, source_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id,
                    record.belief_id,
                    record.domain,
                    record.category,
                    record.predicted_value,
                    record.actual_value,
                    record.error,
                    ts,
                    record.source_id,
                ),
            )
        return record

    def get_accuracy_records(
        self,
        domain: str | None = None,
        category: str | None = None,
        belief_id: str | None = None,
        limit: int = 100,
    ) -> list[AccuracyRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if domain:
            clauses.append("domain=?")
            params.append(domain)
        if category:
            clauses.append("category=?")
            params.append(category)
        if belief_id:
            clauses.append("belief_id=?")
            params.append(belief_id)
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM accuracy_records WHERE {where}"
                " ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            return [_row_to_accuracy_record(r) for r in rows]

    def get_accuracy_record_count(self) -> int:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM accuracy_records"
            ).fetchone()
            return row[0] if row else 0

    def delete_accuracy_records(self, belief_id: str) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM accuracy_records WHERE belief_id=?",
                (belief_id,),
            )

    def get_all_accuracy_records(self, limit: int = 1000) -> list[AccuracyRecord]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM accuracy_records ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_accuracy_record(r) for r in rows]

    # ── Bulk operations ───────────────────────────────────────────────

    def save_all_source_profiles(self, profiles: list[SourceProfile]) -> None:
        for p in profiles:
            self.save_source_profile(p)

    def save_all_accuracy_records(self, records: list[AccuracyRecord]) -> None:
        for r in records:
            self.save_accuracy_record(r)

    def get_statistics(self) -> dict[str, Any]:
        return {
            "source_profiles": self.source_profile_count(),
            "accuracy_records": self.get_accuracy_record_count(),
        }


def _row_to_source_profile(row: sqlite3.Row) -> SourceProfile:
    return SourceProfile(
        source_id=row["source_id"],
        source_type=SourceType(row["source_type"]),
        reliability_score=row["reliability_score"],
        domain_scores=json.loads(row["domain_scores_json"]),
        total_references=row["total_references"],
        correct_references=row["correct_references"],
        contradictory_references=row["contradictory_references"],
        first_seen=_parse_dt(row["first_seen"]),
        last_seen=_parse_dt(row["last_seen"]),
    )


def _row_to_accuracy_record(row: sqlite3.Row) -> AccuracyRecord:
    return AccuracyRecord(
        record_id=row["record_id"],
        belief_id=row["belief_id"],
        domain=row["domain"],
        category=row["category"],
        predicted_value=row["predicted_value"],
        actual_value=row["actual_value"],
        error=row["error"],
        timestamp=_parse_dt(row["timestamp"]) or datetime.utcnow(),
        source_id=row["source_id"],
    )


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None
