from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any

from core.providers.feedback.models import (
    CalibrationEntry, RoutingDecision, RoutingOutcome, ScoreBreakdown,
    _CONTEXT_FALLBACK_CHAIN, _extract_context,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".jarvis", "feedback.db",
)


class FeedbackStore:
    """SQLite-backed persistence for routing decisions, outcomes, and calibrations."""

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
            CREATE TABLE IF NOT EXISTS routing_decisions (
                decision_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL DEFAULT '',
                capability TEXT NOT NULL DEFAULT '',
                task_json TEXT NOT NULL DEFAULT '{}',
                selected_provider TEXT NOT NULL DEFAULT '',
                candidate_scores_json TEXT NOT NULL DEFAULT '[]',
                excluded_providers_json TEXT NOT NULL DEFAULT '[]',
                timestamp REAL NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS routing_outcomes (
                outcome_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                duration_ms REAL NOT NULL DEFAULT 0,
                quality_score REAL NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                retries INTEGER NOT NULL DEFAULT 0,
                replan_level INTEGER NOT NULL DEFAULT 0,
                timestamp REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (decision_id) REFERENCES routing_decisions(decision_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calibration_entries (
                entry_id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                adjustment REAL NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                last_updated REAL NOT NULL DEFAULT 0,
                language TEXT NOT NULL DEFAULT '',
                framework TEXT NOT NULL DEFAULT '',
                project_size TEXT NOT NULL DEFAULT '',
                UNIQUE(provider_id, capability, language, framework, project_size)
            )
        """)
        # Migrate old tables that don't have context columns
        self._migrate_calibration_columns(conn)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_decision
            ON routing_outcomes(decision_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_calibration_lookup
            ON calibration_entries(provider_id, capability, language, framework)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_timestamp
            ON routing_decisions(timestamp)
        """)

    def _migrate_calibration_columns(self, conn: sqlite3.Connection) -> None:
        pragma = conn.execute("PRAGMA table_info(calibration_entries)").fetchall()
        existing = {row["name"] for row in pragma}
        for col, col_type in [("language", "TEXT NOT NULL DEFAULT ''"),
                               ("framework", "TEXT NOT NULL DEFAULT ''"),
                               ("project_size", "TEXT NOT NULL DEFAULT ''")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE calibration_entries ADD COLUMN {col} {col_type}")
                logger.info("[FeedbackStore] Added missing column: %s", col)

    # ── Decisions ──────────────────────────────────────────────────

    def save_decision(self, decision: RoutingDecision) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO routing_decisions
               (decision_id, goal, capability, task_json, selected_provider,
                candidate_scores_json, excluded_providers_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.decision_id,
                decision.goal,
                decision.capability,
                json.dumps(decision.task),
                decision.selected_provider,
                json.dumps([s.to_dict() for s in decision.candidate_scores]),
                json.dumps(decision.excluded_providers),
                decision.timestamp,
            ),
        )

    def get_decision(self, decision_id: str) -> RoutingDecision | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM routing_decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if not row:
            return None
        return RoutingDecision(
            decision_id=row["decision_id"],
            goal=row["goal"],
            capability=row["capability"],
            task=json.loads(row["task_json"]),
            selected_provider=row["selected_provider"],
            candidate_scores=[
                ScoreBreakdown.from_dict(s)
                for s in json.loads(row["candidate_scores_json"])
            ],
            excluded_providers=json.loads(row["excluded_providers_json"]),
            timestamp=row["timestamp"],
        )

    def get_recent_decisions(self, limit: int = 50) -> list[RoutingDecision]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM routing_decisions ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            result.append(RoutingDecision(
                decision_id=row["decision_id"],
                goal=row["goal"],
                capability=row["capability"],
                task=json.loads(row["task_json"]),
                selected_provider=row["selected_provider"],
                candidate_scores=[
                    ScoreBreakdown.from_dict(s)
                    for s in json.loads(row["candidate_scores_json"])
                ],
                excluded_providers=json.loads(row["excluded_providers_json"]),
                timestamp=row["timestamp"],
            ))
        return result

    def count_decisions(self, capability: str | None = None) -> int:
        conn = self._get_conn()
        if capability:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM routing_decisions WHERE capability = ?",
                (capability,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM routing_decisions").fetchone()
        return row["cnt"] if row else 0

    # ── Outcomes ───────────────────────────────────────────────────

    def save_outcome(self, outcome: RoutingOutcome) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO routing_outcomes
               (outcome_id, decision_id, success, duration_ms,
                quality_score, cost, error, retries, replan_level, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                outcome.outcome_id,
                outcome.decision_id,
                1 if outcome.success else 0,
                outcome.duration_ms,
                outcome.quality_score,
                outcome.cost,
                outcome.error,
                outcome.retries,
                outcome.replan_level,
                outcome.timestamp,
            ),
        )

    def get_outcomes_for_decision(self, decision_id: str) -> list[RoutingOutcome]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM routing_outcomes WHERE decision_id = ? ORDER BY timestamp",
            (decision_id,),
        ).fetchall()
        result = []
        for row in rows:
            result.append(RoutingOutcome(
                outcome_id=row["outcome_id"],
                decision_id=row["decision_id"],
                success=bool(row["success"]),
                duration_ms=row["duration_ms"],
                quality_score=row["quality_score"],
                cost=row["cost"],
                error=row["error"],
                retries=row["retries"],
                replan_level=row["replan_level"],
                timestamp=row["timestamp"],
            ))
        return result

    def get_all_outcomes(
        self,
        provider_id: str | None = None,
        capability: str | None = None,
        limit: int = 1000,
    ) -> list[RoutingOutcome]:
        conn = self._get_conn()
        if provider_id and capability:
            rows = conn.execute(
                """SELECT o.* FROM routing_outcomes o
                   JOIN routing_decisions d ON o.decision_id = d.decision_id
                   WHERE d.selected_provider = ? AND d.capability = ?
                   ORDER BY o.timestamp DESC LIMIT ?""",
                (provider_id, capability, limit),
            ).fetchall()
        elif provider_id:
            rows = conn.execute(
                """SELECT o.* FROM routing_outcomes o
                   JOIN routing_decisions d ON o.decision_id = d.decision_id
                   WHERE d.selected_provider = ?
                   ORDER BY o.timestamp DESC LIMIT ?""",
                (provider_id, limit),
            ).fetchall()
        elif capability:
            rows = conn.execute(
                """SELECT o.* FROM routing_outcomes o
                   JOIN routing_decisions d ON o.decision_id = d.decision_id
                   WHERE d.capability = ?
                   ORDER BY o.timestamp DESC LIMIT ?""",
                (capability, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM routing_outcomes ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            result.append(RoutingOutcome(
                outcome_id=row["outcome_id"],
                decision_id=row["decision_id"],
                success=bool(row["success"]),
                duration_ms=row["duration_ms"],
                quality_score=row["quality_score"],
                cost=row["cost"],
                error=row["error"],
                retries=row["retries"],
                replan_level=row["replan_level"],
                timestamp=row["timestamp"],
            ))
        return result

    # ── Calibration (context-aware) ────────────────────────────────

    def _calibration_where(
        self, provider_id: str, capability: str,
        language: str = "", framework: str = "", project_size: str = "",
    ) -> tuple[str, list]:
        """Build WHERE clause and params for exact calibration match."""
        return (
            "provider_id = ? AND capability = ? AND language = ? AND framework = ? AND project_size = ?",
            [provider_id, capability, language, framework, project_size],
        )

    def save_calibration(self, entry: CalibrationEntry) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO calibration_entries
               (entry_id, provider_id, capability, adjustment,
                confidence, evidence_count, last_updated,
                language, framework, project_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.entry_id,
                entry.provider_id,
                entry.capability,
                entry.adjustment,
                entry.confidence,
                entry.evidence_count,
                entry.last_updated,
                entry.language,
                entry.framework,
                entry.project_size,
            ),
        )

    def get_calibration(
        self, provider_id: str, capability: str,
        language: str = "", framework: str = "", project_size: str = "",
    ) -> CalibrationEntry | None:
        """Get calibration matching the exact context. Returns None if no match."""
        conn = self._get_conn()
        where, params = self._calibration_where(
            provider_id, capability, language, framework, project_size,
        )
        row = conn.execute(
            f"SELECT * FROM calibration_entries WHERE {where}",
            params,
        ).fetchone()
        if not row:
            return None
        return self._row_to_calibration(row)

    def get_calibration_fallback(
        self, provider_id: str, capability: str,
        language: str = "", framework: str = "", project_size: str = "",
    ) -> CalibrationEntry | None:
        """Walk the fallback chain from most to least specific context.
        Returns the first match found.
        """
        conn = self._get_conn()
        ctx = {"language": language, "framework": framework, "project_size": project_size}

        for inc_lang, inc_fw, inc_size in _CONTEXT_FALLBACK_CHAIN:
            where_parts = ["provider_id = ?", "capability = ?"]
            params: list = [provider_id, capability]

            lang_val = ctx["language"] if inc_lang else ""
            fw_val = ctx["framework"] if inc_fw else ""
            sz_val = ctx["project_size"] if inc_size else ""

            where_parts.append("language = ?")
            params.append(lang_val)
            where_parts.append("framework = ?")
            params.append(fw_val)
            where_parts.append("project_size = ?")
            params.append(sz_val)

            row = conn.execute(
                f"SELECT * FROM calibration_entries WHERE {' AND '.join(where_parts)}",
                params,
            ).fetchone()
            if row:
                return self._row_to_calibration(row)
        return None

    def _row_to_calibration(self, row: sqlite3.Row) -> CalibrationEntry:
        return CalibrationEntry(
            entry_id=row["entry_id"],
            provider_id=row["provider_id"],
            capability=row["capability"],
            adjustment=row["adjustment"],
            confidence=row["confidence"],
            evidence_count=row["evidence_count"],
            last_updated=row["last_updated"],
            language=row["language"],
            framework=row["framework"],
            project_size=row["project_size"],
        )

    def get_all_calibrations(self) -> list[CalibrationEntry]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM calibration_entries ORDER BY provider_id, capability, language, framework",
        ).fetchall()
        return [self._row_to_calibration(r) for r in rows]

    # ── Analytics ──────────────────────────────────────────────────

    def get_provider_stats(
        self, provider_id: str, capability: str | None = None,
    ) -> dict[str, Any]:
        outcomes = self.get_all_outcomes(provider_id=provider_id, capability=capability)
        if not outcomes:
            return {
                "provider_id": provider_id,
                "total": 0,
                "success_count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_quality": 0.0,
                "avg_cost": 0.0,
            }
        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        return {
            "provider_id": provider_id,
            "total": total,
            "success_count": successes,
            "success_rate": successes / total if total else 0.0,
            "avg_duration_ms": sum(o.duration_ms for o in outcomes) / total,
            "avg_quality": sum(o.quality_score for o in outcomes) / total,
            "avg_cost": sum(o.cost for o in outcomes) / total,
        }

    def get_calibration_summary(self) -> list[dict[str, Any]]:
        entries = self.get_all_calibrations()
        return [
            {
                "provider_id": e.provider_id,
                "capability": e.capability,
                "adjustment": round(e.adjustment, 4),
                "confidence": round(e.confidence, 2),
                "evidence_count": e.evidence_count,
                "language": e.language,
                "framework": e.framework,
            }
            for e in entries
        ]

    def clear(self) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM routing_outcomes")
        conn.execute("DELETE FROM routing_decisions")
        conn.execute("DELETE FROM calibration_entries")

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
