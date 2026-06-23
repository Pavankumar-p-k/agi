"""Self-Modification Engine (Phase 18.0) — Modification Store.

SQLite-backed persistence for modification records.
Lives alongside other JARVIS data in data/workflow.db.

Tables:
  - modification_records: outcome records for each modification attempt
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.self_modification.models import (
    ModificationMetrics,
    ModificationRecord,
    ModificationStatus,
)

logger = logging.getLogger(__name__)

UNIFIED_DB = "data/workflow.db"


class ModificationStore:
    """Persistent storage for self-modification outcomes.

    Thread-safe via reentrant lock.
    """

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
                    CREATE TABLE IF NOT EXISTS modification_records (
                        record_id TEXT PRIMARY KEY,
                        plan_id TEXT NOT NULL,
                        proposal_id TEXT NOT NULL,
                        recipe TEXT NOT NULL,
                        target_system TEXT NOT NULL,
                        target_file TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'planned',
                        before_metrics TEXT NOT NULL DEFAULT '{}',
                        after_metrics TEXT NOT NULL DEFAULT '{}',
                        error_message TEXT NOT NULL DEFAULT '',
                        patch_count INTEGER NOT NULL DEFAULT 0,
                        test_count INTEGER NOT NULL DEFAULT 0,
                        test_passed INTEGER NOT NULL DEFAULT 0,
                        test_failed INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT '',
                        completed_at TEXT NOT NULL DEFAULT ''
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mod_records_status
                    ON modification_records(status)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mod_records_system
                    ON modification_records(target_system)
                """)
                conn.commit()
            finally:
                conn.close()

    # ── CRUD ───────────────────────────────────────────────────────────

    def save(self, record: ModificationRecord) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO modification_records
                       (record_id, plan_id, proposal_id, recipe, target_system,
                        target_file, status, before_metrics, after_metrics,
                        error_message, patch_count, test_count, test_passed,
                        test_failed, created_at, completed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.record_id,
                        record.plan_id,
                        record.proposal_id,
                        record.recipe,
                        record.target_system,
                        record.target_file,
                        record.status.value,
                        json.dumps(record.before_metrics),
                        json.dumps(record.after_metrics),
                        record.error_message,
                        record.patch_count,
                        record.test_count,
                        record.test_passed,
                        record.test_failed,
                        record.created_at,
                        record.completed_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, record_id: str) -> ModificationRecord | None:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM modification_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_record(row)
            finally:
                conn.close()

    def list_by_status(
        self,
        status: ModificationStatus | None = None,
        limit: int = 50,
    ) -> list[ModificationRecord]:
        with self._lock:
            conn = self._get_conn()
            try:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM modification_records WHERE status = ? "
                        "ORDER BY created_at DESC LIMIT ?",
                        (status.value, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM modification_records "
                        "ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [self._row_to_record(r) for r in rows]
            finally:
                conn.close()

    def list_by_system(
        self,
        target_system: str,
        limit: int = 20,
    ) -> list[ModificationRecord]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM modification_records WHERE target_system = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (target_system, limit),
                ).fetchall()
                return [self._row_to_record(r) for r in rows]
            finally:
                conn.close()

    def count_by_status(self) -> dict[str, int]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS cnt FROM modification_records "
                    "GROUP BY status"
                ).fetchall()
                return {r["status"]: r["cnt"] for r in rows}
            finally:
                conn.close()

    def delete(self, record_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM modification_records WHERE record_id = ?",
                    (record_id,),
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
                    "SELECT COUNT(*) AS cnt FROM modification_records"
                ).fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    # ── Helpers ────────────────────────────────────────────────────────

    def _row_to_record(self, row: sqlite3.Row) -> ModificationRecord:
        return ModificationRecord(
            record_id=row["record_id"],
            plan_id=row["plan_id"],
            proposal_id=row["proposal_id"],
            recipe=row["recipe"],
            target_system=row["target_system"],
            target_file=row["target_file"],
            status=ModificationStatus(row["status"]),
            before_metrics=json.loads(row["before_metrics"] or "{}"),
            after_metrics=json.loads(row["after_metrics"] or "{}"),
            error_message=row["error_message"],
            patch_count=row["patch_count"],
            test_count=row["test_count"],
            test_passed=row["test_passed"],
            test_failed=row["test_failed"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
