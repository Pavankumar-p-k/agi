"""Persistent stores for workflow learning outcomes and calibrations.

WorkflowHistoryStore is append-only: each workflow_id may be recorded once.
WorkflowCalibrationStore holds upserted aggregates per
(template_id, template_version, fingerprint_key).
"""

from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import time
from typing import Any

from core.workflow.learning_models import (
    RecoveryMode,
    WorkflowFingerprint,
    WorkflowOutcome,
    _FINGERPRINT_FALLBACK_CHAIN,
    _fingerprint_fallback_key,
)

_OUTCOME_FIELDS = {
    f.name for f in dataclasses.fields(WorkflowOutcome)
} - {"fingerprint", "workflow_id"}


def _mode_value(mode: Any) -> str:
    if isinstance(mode, RecoveryMode):
        return mode.value
    return str(mode)


def _outcome_json(outcome: WorkflowOutcome) -> str:
    data = {
        name: getattr(outcome, name)
        for name in _OUTCOME_FIELDS
    }
    data["recovery_mode"] = _mode_value(outcome.recovery_mode)
    return json.dumps(data)


def _rebuild_fingerprint(key: str) -> WorkflowFingerprint | None:
    """Rebuild a fingerprint from a stored context key (all dimensions)."""
    if not key:
        return None
    fp = WorkflowFingerprint()
    list_dims = {
        "l": "languages",
        "f": "frameworks",
        "p": "capabilities",
        "a": "artifact_types",
        "r": "requirements",
    }
    scalar_dims = {
        "t": "task_type",
        "c": "complexity",
        "s": "project_size",
    }
    for segment in key.split("|"):
        if ":" not in segment:
            continue
        prefix, value = segment.split(":", 1)
        if not value:
            continue
        if prefix in scalar_dims:
            setattr(fp, scalar_dims[prefix], value)
        elif prefix in list_dims:
            setattr(
                fp,
                list_dims[prefix],
                [item for item in value.split(",") if item],
            )
    return fp


def _row_to_outcome(row: sqlite3.Row) -> WorkflowOutcome:
    data = json.loads(row["outcome_json"] or "{}")
    data = {k: v for k, v in data.items() if k in _OUTCOME_FIELDS}
    if "recovery_mode" in data:
        data["recovery_mode"] = RecoveryMode(data["recovery_mode"])
    fingerprint = _rebuild_fingerprint(row["fingerprint_key"] or "")
    return WorkflowOutcome(
        workflow_id=row["workflow_id"],
        fingerprint=fingerprint,
        **data,
    )


class WorkflowHistoryStore:
    """Append-only store of workflow outcomes."""

    def __init__(self, db_path: str = "data/workflow_history.db") -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_history (
                workflow_id TEXT PRIMARY KEY,
                template_id TEXT NOT NULL DEFAULT '',
                template_version INTEGER NOT NULL DEFAULT 1,
                fingerprint_key TEXT NOT NULL DEFAULT '',
                outcome_json TEXT NOT NULL DEFAULT '{}',
                timestamp REAL NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                recovery_mode TEXT NOT NULL DEFAULT 'FIRST_TRY'
            )
            """
        )

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def save_outcome(self, outcome: WorkflowOutcome) -> None:
        self._insert(
            workflow_id=outcome.workflow_id,
            template_id=outcome.template_id,
            template_version=outcome.template_version,
            fingerprint_key=outcome.fingerprint_key,
            outcome_json=_outcome_json(outcome),
            timestamp=time.time(),
            success=bool(outcome.success),
            recovery_mode=_mode_value(outcome.recovery_mode),
        )

    def save_outcome_direct(
        self,
        workflow_id: str,
        template_id: str = "",
        template_version: int = 1,
        fingerprint_key: str = "",
        outcome_json: str = "{}",
        timestamp: float | None = None,
        success: bool = False,
        recovery_mode: str = "FIRST_TRY",
    ) -> None:
        self._insert(
            workflow_id=workflow_id,
            template_id=template_id,
            template_version=template_version,
            fingerprint_key=fingerprint_key or "",
            outcome_json=outcome_json or "{}",
            timestamp=time.time() if timestamp is None else timestamp,
            success=bool(success),
            recovery_mode=_mode_value(recovery_mode),
        )

    def _insert(
        self,
        workflow_id: str,
        template_id: str,
        template_version: int,
        fingerprint_key: str,
        outcome_json: str,
        timestamp: float,
        success: bool,
        recovery_mode: str,
    ) -> None:
        try:
            self._conn.execute(
                """
                INSERT INTO workflow_history
                    (workflow_id, template_id, template_version,
                     fingerprint_key, outcome_json, timestamp,
                     success, recovery_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    template_id,
                    int(template_version),
                    fingerprint_key,
                    outcome_json,
                    float(timestamp),
                    int(bool(success)),
                    recovery_mode,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"outcome for workflow {workflow_id!r} already exists"
            ) from exc

    def get_outcome(self, workflow_id: str) -> WorkflowOutcome | None:
        row = self._conn.execute(
            "SELECT * FROM workflow_history WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_outcome(row)

    def _where(
        self,
        template_id: str | None = None,
        template_version: int | None = None,
        success: bool | None = None,
        recovery_mode: Any = None,
        fingerprint_key: str | None = None,
        min_timestamp: float | None = None,
        max_timestamp: float | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if template_id is not None:
            clauses.append("template_id = ?")
            params.append(template_id)
        if template_version is not None:
            clauses.append("template_version = ?")
            params.append(int(template_version))
        if success is not None:
            clauses.append("success = ?")
            params.append(int(bool(success)))
        if recovery_mode is not None:
            clauses.append("recovery_mode = ?")
            params.append(_mode_value(recovery_mode))
        if fingerprint_key is not None:
            clauses.append("fingerprint_key = ?")
            params.append(fingerprint_key)
        if min_timestamp is not None:
            clauses.append("timestamp >= ?")
            params.append(float(min_timestamp))
        if max_timestamp is not None:
            clauses.append("timestamp <= ?")
            params.append(float(max_timestamp))
        where = ""
        if clauses:
            where = " WHERE " + " AND ".join(clauses)
        return where, params

    def get_outcomes(
        self,
        template_id: str | None = None,
        template_version: int | None = None,
        success: bool | None = None,
        recovery_mode: Any = None,
        fingerprint_key: str | None = None,
        min_timestamp: float | None = None,
        max_timestamp: float | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkflowOutcome]:
        where, params = self._where(
            template_id, template_version, success, recovery_mode,
            fingerprint_key, min_timestamp, max_timestamp,
        )
        sql = f"SELECT * FROM workflow_history{where} ORDER BY rowid ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = params + [int(limit), int(offset)]
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params = params + [int(offset)]
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_outcome(row) for row in rows]

    def count_outcomes(
        self,
        template_id: str | None = None,
        template_version: int | None = None,
        success: bool | None = None,
        recovery_mode: Any = None,
        fingerprint_key: str | None = None,
        min_timestamp: float | None = None,
        max_timestamp: float | None = None,
    ) -> int:
        where, params = self._where(
            template_id, template_version, success, recovery_mode,
            fingerprint_key, min_timestamp, max_timestamp,
        )
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM workflow_history{where}", params
        ).fetchone()
        return int(row["n"])

    def compute_stats(self, template_id: str) -> dict:
        outcomes = self.get_outcomes(template_id=template_id)
        total = len(outcomes)
        if total == 0:
            return {
                "total": 0,
                "success_count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_cost": 0.0,
                "avg_quality": 0.0,
                "recovery_counts": {},
                "error_categories": set(),
            }
        success_count = sum(1 for o in outcomes if o.success)
        recovery_counts: dict[str, int] = {}
        error_categories: set[str] = set()
        for outcome in outcomes:
            mode = _mode_value(outcome.recovery_mode)
            recovery_counts[mode] = recovery_counts.get(mode, 0) + 1
            error_categories.update(outcome.error_categories)
        return {
            "total": total,
            "success_count": success_count,
            "success_rate": success_count / total,
            "avg_duration_ms": sum(o.duration_ms for o in outcomes) / total,
            "avg_cost": sum(o.cost for o in outcomes) / total,
            "avg_quality": sum(o.quality for o in outcomes) / total,
            "recovery_counts": recovery_counts,
            "error_categories": error_categories,
        }

    def clear(self) -> None:
        self._conn.execute("DELETE FROM workflow_history")

    def close(self) -> None:
        self._conn.close()


class WorkflowCalibrationStore:
    """Upserted calibration aggregates per template/fingerprint."""

    def __init__(self, db_path: str = "data/workflow_calibration.db") -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, isolation_level=None,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id TEXT NOT NULL,
                template_version INTEGER NOT NULL DEFAULT 1,
                fingerprint_key TEXT NOT NULL DEFAULT '',
                task_type TEXT NOT NULL DEFAULT '',
                project_size TEXT NOT NULL DEFAULT '',
                languages TEXT NOT NULL DEFAULT '',
                frameworks TEXT NOT NULL DEFAULT '',
                success_rate REAL NOT NULL DEFAULT 0.0,
                avg_duration_ms REAL NOT NULL DEFAULT 0.0,
                avg_cost REAL NOT NULL DEFAULT 0.0,
                avg_quality REAL NOT NULL DEFAULT 0.0,
                first_try_rate REAL NOT NULL DEFAULT 0.0,
                recovered_rate REAL NOT NULL DEFAULT 0.0,
                confidence REAL NOT NULL DEFAULT 0.0,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                UNIQUE (template_id, template_version, fingerprint_key)
            )
            """
        )

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def save_calibration(
        self,
        template_id: str,
        template_version: int = 1,
        fingerprint_key: str = "",
        task_type: str = "",
        project_size: str = "",
        languages: str = "",
        frameworks: str = "",
        success_rate: float = 0.0,
        avg_duration_ms: float = 0.0,
        avg_cost: float = 0.0,
        avg_quality: float = 0.0,
        first_try_rate: float = 0.0,
        recovered_rate: float = 0.0,
        confidence: float = 0.0,
        evidence_count: int = 0,
        updated_at: float | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO workflow_calibration
                (template_id, template_version, fingerprint_key,
                 task_type, project_size, languages, frameworks,
                 success_rate, avg_duration_ms, avg_cost, avg_quality,
                 first_try_rate, recovered_rate, confidence,
                 evidence_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (template_id, template_version, fingerprint_key)
            DO UPDATE SET
                task_type = excluded.task_type,
                project_size = excluded.project_size,
                languages = excluded.languages,
                frameworks = excluded.frameworks,
                success_rate = excluded.success_rate,
                avg_duration_ms = excluded.avg_duration_ms,
                avg_cost = excluded.avg_cost,
                avg_quality = excluded.avg_quality,
                first_try_rate = excluded.first_try_rate,
                recovered_rate = excluded.recovered_rate,
                confidence = excluded.confidence,
                evidence_count = excluded.evidence_count,
                updated_at = excluded.updated_at
            """,
            (
                template_id,
                int(template_version),
                fingerprint_key or "",
                task_type,
                project_size,
                languages,
                frameworks,
                float(success_rate),
                float(avg_duration_ms),
                float(avg_cost),
                float(avg_quality),
                float(first_try_rate),
                float(recovered_rate),
                float(confidence),
                int(evidence_count),
                time.time() if updated_at is None else float(updated_at),
            ),
        )

    def get_calibration(
        self,
        template_id: str,
        template_version: int = 1,
        fingerprint_key: str = "",
    ) -> dict | None:
        row = self._conn.execute(
            """
            SELECT * FROM workflow_calibration
            WHERE template_id = ? AND template_version = ?
              AND fingerprint_key = ?
            """,
            (template_id, int(template_version), fingerprint_key or ""),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_calibration_fallback(
        self,
        template_id: str,
        template_version: int = 1,
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
    ) -> dict | None:
        for mask_task, mask_lang, mask_fw, mask_size in (
            _FINGERPRINT_FALLBACK_CHAIN
        ):
            key = _fingerprint_fallback_key(
                task_type=task_type if mask_task else "",
                languages=languages if mask_lang else "",
                frameworks=frameworks if mask_fw else "",
                project_size=project_size if mask_size else "",
            )
            cal = self.get_calibration(
                template_id=template_id,
                template_version=template_version,
                fingerprint_key=key,
            )
            if cal is not None:
                return cal
        return None

    def list_calibrations(
        self, template_id: str | None = None
    ) -> list[dict]:
        if template_id is None:
            rows = self._conn.execute(
                "SELECT * FROM workflow_calibration "
                "ORDER BY evidence_count DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM workflow_calibration "
                "WHERE template_id = ? ORDER BY evidence_count DESC",
                (template_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_summary(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT template_id, template_version, fingerprint_key,
                   success_rate, confidence, avg_duration_ms,
                   evidence_count, updated_at
            FROM workflow_calibration
            ORDER BY evidence_count DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM workflow_calibration")

    def close(self) -> None:
        self._conn.close()
