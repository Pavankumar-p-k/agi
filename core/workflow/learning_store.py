from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any

from core.workflow.learning_models import (
    WorkflowOutcome, RecoveryMode,
    WorkflowFingerprint,
    _FINGERPRINT_FALLBACK_CHAIN, _fingerprint_fallback_key,
    _parse_fingerprint_key,
)

logger = logging.getLogger(__name__)


def _ensure_provider_list(val: Any) -> list[dict[str, Any]]:
    """Normalize provider_summary to a list of dicts.

    Handles backward compatibility with old data stored as
    bare dicts (e.g. {"forge": True}) by converting to empty
    list — old dict format is not meaningful as provider entries.
    """
    if isinstance(val, list):
        return [dict(e) if not isinstance(e, dict) else e for e in val]
    return []


_DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".jarvis", "workflow_learning.db",
)


# ── WorkflowHistoryStore (append-only source of truth) ────────────────


class WorkflowHistoryStore:
    """Append-only store for immutable WorkflowOutcome records.

    Never updates or deletes records. The source of truth for
    workflow-level learning.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.isolation_level = None
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_history (
                workflow_id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL DEFAULT '',
                template_version INTEGER NOT NULL DEFAULT 1,
                fingerprint_key TEXT NOT NULL DEFAULT '',
                outcome_json TEXT NOT NULL DEFAULT '{}',
                timestamp REAL NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0,
                recovery_mode TEXT NOT NULL DEFAULT 'FIRST_TRY'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_template
            ON workflow_history(template_id, template_version)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_fingerprint
            ON workflow_history(fingerprint_key)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_timestamp
            ON workflow_history(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_success
            ON workflow_history(success)
        """)

    # ── Write (append-only) ─────────────────────────────────────────

    def save_outcome(self, outcome: WorkflowOutcome) -> None:
        """Append an outcome record. Raises if workflow_id already exists."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT 1 FROM workflow_history WHERE workflow_id = ?",
            (outcome.workflow_id,),
        ).fetchone()
        if existing:
            raise ValueError(
                f"WorkflowOutcome {outcome.workflow_id} already exists "
                "(history is append-only)"
            )
        outcome_dict = self._outcome_to_dict(outcome)
        conn.execute(
            """INSERT INTO workflow_history
               (workflow_id, template_id, template_version,
                fingerprint_key, outcome_json, timestamp, success,
                recovery_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                outcome.workflow_id,
                outcome.template_id,
                outcome.template_version,
                outcome.fingerprint_key,
                json.dumps(outcome_dict),
                time.time(),
                1 if outcome.success else 0,
                outcome.recovery_mode.value,
            ),
        )

    def save_outcome_direct(
        self,
        workflow_id: str,
        template_id: str = "",
        template_version: int = 1,
        fingerprint_key: str = "",
        outcome_json: str = "{}",
        timestamp: float = 0.0,
        success: bool = False,
        recovery_mode: str = "FIRST_TRY",
    ) -> None:
        """Raw insert with pre-computed values. Useful for recorder."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT 1 FROM workflow_history WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if existing:
            raise ValueError(
                f"WorkflowOutcome {workflow_id} already exists "
                "(history is append-only)"
            )
        conn.execute(
            """INSERT INTO workflow_history
               (workflow_id, template_id, template_version,
                fingerprint_key, outcome_json, timestamp, success,
                recovery_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_id, template_id, template_version,
                fingerprint_key, outcome_json, timestamp,
                1 if success else 0, recovery_mode,
            ),
        )

    # ── Queries ─────────────────────────────────────────────────────

    def get_outcome(self, workflow_id: str) -> WorkflowOutcome | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM workflow_history WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_outcome(row)

    def get_outcomes(
        self,
        template_id: str | None = None,
        template_version: int | None = None,
        fingerprint_key: str | None = None,
        success: bool | None = None,
        recovery_mode: str | None = None,
        min_timestamp: float | None = None,
        max_timestamp: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkflowOutcome]:
        conn = self._get_conn()
        where_parts: list[str] = []
        params: list[Any] = []

        if template_id is not None:
            where_parts.append("template_id = ?")
            params.append(template_id)
        if template_version is not None:
            where_parts.append("template_version = ?")
            params.append(template_version)
        if fingerprint_key is not None:
            where_parts.append("fingerprint_key = ?")
            params.append(fingerprint_key)
        if success is not None:
            where_parts.append("success = ?")
            params.append(1 if success else 0)
        if recovery_mode is not None:
            where_parts.append("recovery_mode = ?")
            params.append(recovery_mode)
        if min_timestamp is not None:
            where_parts.append("timestamp >= ?")
            params.append(min_timestamp)
        if max_timestamp is not None:
            where_parts.append("timestamp <= ?")
            params.append(max_timestamp)

        where_sql = " AND ".join(where_parts) if where_parts else "1=1"
        rows = conn.execute(
            f"SELECT * FROM workflow_history WHERE {where_sql}"
            " ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [self._row_to_outcome(r) for r in rows]

    def count_outcomes(
        self,
        template_id: str | None = None,
        template_version: int | None = None,
        fingerprint_key: str | None = None,
        success: bool | None = None,
    ) -> int:
        conn = self._get_conn()
        where_parts: list[str] = []
        params: list[Any] = []

        if template_id is not None:
            where_parts.append("template_id = ?")
            params.append(template_id)
        if template_version is not None:
            where_parts.append("template_version = ?")
            params.append(template_version)
        if fingerprint_key is not None:
            where_parts.append("fingerprint_key = ?")
            params.append(fingerprint_key)
        if success is not None:
            where_parts.append("success = ?")
            params.append(1 if success else 0)

        where_sql = " AND ".join(where_parts) if where_parts else "1=1"
        row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM workflow_history WHERE {where_sql}",
            params,
        ).fetchone()
        return row["cnt"] if row else 0

    def get_outcomes_for_fingerprint_fallback(
        self,
        template_id: str,
        fingerprint_key: str,
        limit: int = 1000,
    ) -> list[WorkflowOutcome]:
        """Query outcomes matching template_id and fingerprint_key."""
        return self.get_outcomes(
            template_id=template_id,
            fingerprint_key=fingerprint_key,
            limit=limit,
        )

    # ── Aggregation helpers ─────────────────────────────────────────

    def compute_stats(
        self,
        template_id: str,
        template_version: int | None = None,
        fingerprint_key: str | None = None,
    ) -> dict[str, Any]:
        """Compute aggregate statistics from history for a given scope.

        Returns dict with: total, success_count, success_rate,
        avg_duration_ms, avg_cost, avg_quality, recovery_counts,
        error_categories.
        """
        outcomes = self.get_outcomes(
            template_id=template_id,
            template_version=template_version,
            fingerprint_key=fingerprint_key,
            limit=10000,
        )
        if not outcomes:
            return {
                "total": 0,
                "success_count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_cost": 0.0,
                "avg_quality": 0.0,
                "recovery_counts": {},
                "error_categories": [],
            }

        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        recovery_counts: dict[str, int] = {}
        error_cat_set: dict[str, int] = {}

        for o in outcomes:
            r = o.recovery_mode.value if isinstance(o.recovery_mode, RecoveryMode) else str(o.recovery_mode)
            recovery_counts[r] = recovery_counts.get(r, 0) + 1
            for ec in o.error_categories:
                error_cat_set[ec] = error_cat_set.get(ec, 0) + 1

        return {
            "total": total,
            "success_count": successes,
            "success_rate": successes / total if total else 0.0,
            "avg_duration_ms": sum(o.duration_ms for o in outcomes) / total,
            "avg_cost": sum(o.cost for o in outcomes) / total,
            "avg_quality": sum(o.quality for o in outcomes) / total,
            "recovery_counts": recovery_counts,
            "error_categories": sorted(error_cat_set.keys()),
        }

    # ── Internal helpers ────────────────────────────────────────────

    def _outcome_to_dict(self, o: WorkflowOutcome) -> dict[str, Any]:
        return {
            "workflow_id": o.workflow_id,
            "template_id": o.template_id,
            "template_version": o.template_version,
            "fingerprint_key": o.fingerprint_key,
            "success": o.success,
            "duration_ms": o.duration_ms,
            "cost": o.cost,
            "quality": o.quality,
            "recovery_mode": o.recovery_mode.value if isinstance(o.recovery_mode, RecoveryMode) else o.recovery_mode,
            "artifacts": o.artifacts,
            "error_categories": o.error_categories,
            "provider_summary": o.provider_summary,
            "activity_graph_id": o.activity_graph_id,
        }

    def _row_to_outcome(self, row: sqlite3.Row) -> WorkflowOutcome:
        raw = json.loads(row["outcome_json"])
        raw_wf = row["workflow_id"]
        # Reconstruct the fingerprint from stored key string
        fk = raw.get("fingerprint_key", row["fingerprint_key"])
        fp = None
        if fk:
            from core.workflow.learning_models import WorkflowFingerprint
            parsed = _parse_fingerprint_key(fk)
            fp = WorkflowFingerprint(
                task_type=parsed.get("task_type", ""),
                languages=parsed["languages"].split(",") if parsed.get("languages") else [],
                frameworks=parsed["frameworks"].split(",") if parsed.get("frameworks") else [],
                project_size=parsed.get("project_size", ""),
            )
        return WorkflowOutcome(
            workflow_id=raw_wf,
            template_id=raw.get("template_id", row["template_id"]),
            template_version=raw.get("template_version", row["template_version"]),
            fingerprint=fp,
            success=raw.get("success", bool(row["success"])),
            duration_ms=raw.get("duration_ms", 0.0),
            cost=raw.get("cost", 0.0),
            quality=raw.get("quality", 0.0),
            recovery_mode=RecoveryMode(raw.get("recovery_mode", row["recovery_mode"])),
            artifacts=raw.get("artifacts", []),
            error_categories=raw.get("error_categories", []),
            provider_summary=_ensure_provider_list(raw.get("provider_summary", [])),
            activity_graph_id=raw.get("activity_graph_id", ""),
        )

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def clear(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM workflow_history")


# ── WorkflowCalibrationStore (derived cache) ──────────────────────────


class WorkflowCalibrationStore:
    """Cached calibration statistics derived from WorkflowHistoryStore.

    Values can always be recomputed from history. This is a performance
    cache with fallback-keyed lookup (mirrors ProviderCalibrationStore).
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.isolation_level = None
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT NOT NULL DEFAULT '',
                template_version INTEGER NOT NULL DEFAULT 1,
                fingerprint_key TEXT NOT NULL DEFAULT '',
                task_type TEXT NOT NULL DEFAULT '',
                languages TEXT NOT NULL DEFAULT '',
                frameworks TEXT NOT NULL DEFAULT '',
                project_size TEXT NOT NULL DEFAULT '',
                success_rate REAL NOT NULL DEFAULT 0.0,
                avg_duration_ms REAL NOT NULL DEFAULT 0.0,
                avg_cost REAL NOT NULL DEFAULT 0.0,
                avg_quality REAL NOT NULL DEFAULT 0.0,
                first_try_rate REAL NOT NULL DEFAULT 0.0,
                recovered_rate REAL NOT NULL DEFAULT 0.0,
                confidence REAL NOT NULL DEFAULT 0.0,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0,
                UNIQUE(template_id, template_version, fingerprint_key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_calibration_lookup
            ON workflow_calibration(template_id, template_version, task_type, languages)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_calibration_fingerprint
            ON workflow_calibration(fingerprint_key)
        """)

    # ── Write ───────────────────────────────────────────────────────

    def save_calibration(
        self,
        template_id: str,
        template_version: int = 1,
        fingerprint_key: str = "",
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
        success_rate: float = 0.0,
        avg_duration_ms: float = 0.0,
        avg_cost: float = 0.0,
        avg_quality: float = 0.0,
        first_try_rate: float = 0.0,
        recovered_rate: float = 0.0,
        confidence: float = 0.0,
        evidence_count: int = 0,
    ) -> None:
        conn = self._get_conn()
        now = __import__("time").time()
        conn.execute(
            """INSERT OR REPLACE INTO workflow_calibration
               (template_id, template_version, fingerprint_key,
                task_type, languages, frameworks, project_size,
                success_rate, avg_duration_ms, avg_cost, avg_quality,
                first_try_rate, recovered_rate, confidence, evidence_count,
                updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                template_id, template_version, fingerprint_key,
                task_type, languages, frameworks, project_size,
                success_rate, avg_duration_ms, avg_cost, avg_quality,
                first_try_rate, recovered_rate, confidence, evidence_count,
                now,
            ),
        )

    # ── Query by key ────────────────────────────────────────────────

    def get_calibration(
        self,
        template_id: str,
        template_version: int = 1,
        fingerprint_key: str = "",
    ) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute(
            """SELECT * FROM workflow_calibration
               WHERE template_id = ? AND template_version = ?
               AND fingerprint_key = ?""",
            (template_id, template_version, fingerprint_key),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    # ── Fallback query (mirrors FeedbackStore pattern) ──────────────

    def get_calibration_fallback(
        self,
        template_id: str,
        template_version: int = 1,
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
    ) -> dict[str, Any] | None:
        """Walk fallback chain to find best matching calibration.

        Starts with the most specific context
        (task_type + languages + frameworks + project_size)
        and progressively relaxes constraints until a match is found.
        """
        conn = self._get_conn()

        for inc_task, inc_lang, inc_fw, inc_size in _FINGERPRINT_FALLBACK_CHAIN:
            where_parts: list[str] = [
                "template_id = ?",
                "template_version = ?",
            ]
            params: list[Any] = [template_id, template_version]

            t_val = task_type if inc_task else ""
            l_val = languages if inc_lang else ""
            f_val = frameworks if inc_fw else ""
            s_val = project_size if inc_size else ""

            where_parts.append("task_type = ?")
            params.append(t_val)
            where_parts.append("languages = ?")
            params.append(l_val)
            where_parts.append("frameworks = ?")
            params.append(f_val)
            where_parts.append("project_size = ?")
            params.append(s_val)

            row = conn.execute(
                f"SELECT * FROM workflow_calibration"
                f" WHERE {' AND '.join(where_parts)}",
                params,
            ).fetchone()
            if row:
                return dict(row)
        return None

    # ── List / Summary ──────────────────────────────────────────────

    def list_calibrations(
        self,
        template_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if template_id:
            rows = conn.execute(
                """SELECT * FROM workflow_calibration
                   WHERE template_id = ?
                   ORDER BY evidence_count DESC LIMIT ?""",
                (template_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM workflow_calibration
                   ORDER BY evidence_count DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self) -> list[dict[str, Any]]:
        entries = self.list_calibrations(limit=1000)
        return [
            {
                "template_id": e["template_id"],
                "template_version": e["template_version"],
                "fingerprint_key": e["fingerprint_key"],
                "success_rate": round(e["success_rate"], 4),
                "avg_duration_ms": round(e["avg_duration_ms"], 1),
                "avg_cost": round(e["avg_cost"], 4),
                "avg_quality": round(e["avg_quality"], 4),
                "confidence": round(e["confidence"], 2),
                "evidence_count": e["evidence_count"],
            }
            for e in entries
        ]

    def clear(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM workflow_calibration")

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
