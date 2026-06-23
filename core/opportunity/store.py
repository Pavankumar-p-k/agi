"""OpportunityStore — SQLite-backed persistence for opportunity outcome records.

Table:
  - opportunity_records: predicted vs actual outcome tracking

Lives in the same database (data/workflow.db) as the belief quality system.
Thread-safe with reentrant lock.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.opportunity.models import OpportunitySource

logger = logging.getLogger(__name__)

UNIFIED_DB = "data/workflow.db"


class OpportunityRecord:
    """Record of an opportunity outcome — enables calibration."""

    def __init__(
        self,
        opportunity_id: str,
        source: str,
        target_system: str,
        predicted_score: float,
        actual_improvement: float,
        actual_success: bool,
        selected_at: str | None = None,
        completed_at: str | None = None,
        prediction_error: float | None = None,
    ):
        self.opportunity_id = opportunity_id
        self.source = source
        self.target_system = target_system
        self.predicted_score = predicted_score
        self.actual_improvement = actual_improvement
        self.actual_success = actual_success
        self.selected_at = selected_at or datetime.now().isoformat()
        self.completed_at = completed_at
        self.prediction_error = prediction_error if prediction_error is not None else (
            predicted_score - actual_improvement
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "source": self.source,
            "target_system": self.target_system,
            "predicted_score": round(self.predicted_score, 3),
            "actual_improvement": round(self.actual_improvement, 3),
            "actual_success": self.actual_success,
            "selected_at": self.selected_at,
            "completed_at": self.completed_at,
            "prediction_error": round(self.prediction_error, 3),
        }


class OpportunityStore:
    """SQLite-backed persistence for opportunity outcome records."""

    def __init__(self, db_path: str | None = None):
        self._db_path = str(db_path or UNIFIED_DB)
        self._lock = threading.RLock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS opportunity_records (
                        opportunity_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        target_system TEXT NOT NULL,
                        predicted_score REAL NOT NULL,
                        actual_improvement REAL NOT NULL DEFAULT 0.0,
                        actual_success INTEGER NOT NULL DEFAULT 0,
                        selected_at TEXT,
                        completed_at TEXT,
                        prediction_error REAL NOT NULL DEFAULT 0.0
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    # ── CRUD ───────────────────────────────────────────────────────────

    def save(self, record: OpportunityRecord) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO opportunity_records
                       (opportunity_id, source, target_system, predicted_score,
                        actual_improvement, actual_success, selected_at,
                        completed_at, prediction_error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.opportunity_id,
                        record.source,
                        record.target_system,
                        record.predicted_score,
                        record.actual_improvement,
                        1 if record.actual_success else 0,
                        record.selected_at,
                        record.completed_at,
                        record.prediction_error,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, opportunity_id: str) -> OpportunityRecord | None:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM opportunity_records WHERE opportunity_id = ?",
                    (opportunity_id,),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_record(row)
            finally:
                conn.close()

    def list_records(
        self,
        source: str | None = None,
        target_system: str | None = None,
        limit: int = 100,
    ) -> list[OpportunityRecord]:
        with self._lock:
            conn = self._get_conn()
            try:
                query = "SELECT * FROM opportunity_records WHERE 1=1"
                params: list[Any] = []
                if source:
                    query += " AND source = ?"
                    params.append(source)
                if target_system:
                    query += " AND target_system = ?"
                    params.append(target_system)
                query += " ORDER BY selected_at DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_record(r) for r in rows]
            finally:
                conn.close()

    def delete(self, opportunity_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM opportunity_records WHERE opportunity_id = ?",
                    (opportunity_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def count(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM opportunity_records"
                ).fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def clear(self) -> None:
        """Clear all records (testing only)."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM opportunity_records")
                conn.commit()
            finally:
                conn.close()

    # ── Helpers ────────────────────────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> OpportunityRecord:
        return OpportunityRecord(
            opportunity_id=row["opportunity_id"],
            source=row["source"],
            target_system=row["target_system"],
            predicted_score=row["predicted_score"],
            actual_improvement=row["actual_improvement"],
            actual_success=bool(row["actual_success"]),
            selected_at=row["selected_at"],
            completed_at=row["completed_at"],
            prediction_error=row["prediction_error"],
        )
