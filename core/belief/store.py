"""SQLite-backed persistence for belief quality data."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from core.belief.models import AccuracyRecord, SourceProfile


class BeliefStore:
    """Persist source profiles and accuracy records in SQLite."""

    def __init__(self, db_path: str = "data/belief.db") -> None:
        self.db_path = db_path
        if db_path and db_path != ":memory:":
            directory = os.path.dirname(os.path.abspath(db_path))
            if directory:
                os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_profiles (
                    source_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accuracy_records (
                    record_id TEXT PRIMARY KEY,
                    belief_id TEXT,
                    domain TEXT,
                    data TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ar_belief ON accuracy_records(belief_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ar_domain ON accuracy_records(domain)"
            )
            self._conn.commit()

    # ── source profiles ──────────────────────────────────────────────

    def save_source_profile(self, profile: SourceProfile) -> None:
        self._with_lock(
            "INSERT OR REPLACE INTO source_profiles (source_id, data) VALUES (?, ?)",
            (profile.source_id, json.dumps(profile.to_dict())),
        )

    def save_all_source_profiles(self, profiles: List[SourceProfile]) -> None:
        for profile in profiles or []:
            if isinstance(profile, dict):
                profile = SourceProfile.from_dict(profile)
            self.save_source_profile(profile)

    def get_source_profile(self, source_id: str) -> Optional[SourceProfile]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM source_profiles WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        return SourceProfile.from_dict(json.loads(row["data"]))

    def get_all_source_profiles(self) -> List[SourceProfile]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM source_profiles"
            ).fetchall()
        return [SourceProfile.from_dict(json.loads(r["data"])) for r in rows]

    def source_profile_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM source_profiles"
            ).fetchone()
        return int(row["n"])

    # ── accuracy records ─────────────────────────────────────────────

    def save_accuracy_record(self, record: AccuracyRecord) -> None:
        self._with_lock(
            "INSERT OR REPLACE INTO accuracy_records "
            "(record_id, belief_id, domain, data) VALUES (?, ?, ?, ?)",
            (
                record.record_id,
                record.belief_id,
                record.domain,
                json.dumps(record.to_dict()),
            ),
        )

    def save_all_accuracy_records(self, records: List[AccuracyRecord]) -> None:
        for record in records or []:
            if isinstance(record, dict):
                record = AccuracyRecord.from_dict(record)
            self.save_accuracy_record(record)

    def get_accuracy_records(
        self,
        domain: Optional[str] = None,
        belief_id: Optional[str] = None,
    ) -> List[AccuracyRecord]:
        query = "SELECT data FROM accuracy_records"
        clauses: List[str] = []
        params: List[Any] = []
        if domain is not None:
            clauses.append("domain = ?")
            params.append(domain)
        if belief_id is not None:
            clauses.append("belief_id = ?")
            params.append(belief_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()
        return [AccuracyRecord.from_dict(json.loads(r["data"])) for r in rows]

    def get_accuracy_record_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM accuracy_records"
            ).fetchone()
        return int(row["n"])

    def delete_accuracy_records(self, belief_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM accuracy_records WHERE belief_id = ?", (belief_id,)
            )
            self._conn.commit()
        return cursor.rowcount

    # ── misc ─────────────────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "source_profiles": self.source_profile_count(),
            "accuracy_records": self.get_accuracy_record_count(),
        }

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM source_profiles")
            self._conn.execute("DELETE FROM accuracy_records")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _with_lock(self, query: str, params: tuple) -> None:
        with self._lock:
            self._conn.execute(query, params)
            self._conn.commit()
