"""Persistence for the decision feedback engine.

Completed from the committed contract in tests/unit/test_provider_feedback.py.

Schema (one SQLite file):
- ``decisions``   — RoutingDecision rows (task context stored as JSON).
- ``outcomes``    — RoutingOutcome rows, joined to decisions for provider/
                    capability-filtered queries.
- ``calibrations``— CalibrationEntry rows, unique per
                    (provider, capability, language, framework, project_size).

Calibration lookups are context-EXACT: an entry saved with
``language="python"`` does not match a generic (no-context) lookup and vice
versa.  ``get_calibration_fallback`` walks the committed
``_CONTEXT_FALLBACK_CHAIN`` (specific → generic), where a chain pattern with a
zeroed dimension only matches entries that are empty (generic) in that
dimension.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from core.providers.feedback.models import (
    CalibrationEntry,
    RoutingDecision,
    RoutingOutcome,
    ScoreBreakdown,
    _CONTEXT_FALLBACK_CHAIN,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL DEFAULT '',
    capability TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '{}',
    selected_provider TEXT NOT NULL DEFAULT '',
    candidate_scores TEXT NOT NULL DEFAULT '[]',
    excluded_providers TEXT NOT NULL DEFAULT '[]',
    timestamp REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0,
    quality_score REAL NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    retries INTEGER NOT NULL DEFAULT 0,
    replan_level INTEGER NOT NULL DEFAULT 0,
    timestamp REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS calibrations (
    entry_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    adjustment REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    last_updated REAL NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT '',
    framework TEXT NOT NULL DEFAULT '',
    project_size TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON outcomes(decision_id);
CREATE INDEX IF NOT EXISTS idx_cal_context
    ON calibrations(provider_id, capability, language, framework, project_size);
"""


class FeedbackStore:
    """SQLite store for routing decisions, outcomes, and calibration entries."""

    def __init__(self, db_path: str | Path = "data/feedback.db") -> None:
        self.db_path = str(db_path)
        parent = Path(self.db_path).parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[feedback_store] close failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Decisions                                                          #
    # ------------------------------------------------------------------ #

    def save_decision(self, decision: RoutingDecision) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO decisions "
            "(decision_id, goal, capability, task, selected_provider, "
            " candidate_scores, excluded_providers, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision.decision_id,
                decision.goal,
                decision.capability,
                json.dumps(decision.task or {}),
                decision.selected_provider,
                json.dumps([c.to_dict() for c in decision.candidate_scores]),
                json.dumps(list(decision.excluded_providers)),
                float(decision.timestamp),
            ),
        )
        self._conn.commit()

    def get_decision(self, decision_id: str) -> Optional[RoutingDecision]:
        row = self._conn.execute(
            "SELECT decision_id, goal, capability, task, selected_provider, "
            "candidate_scores, excluded_providers, timestamp "
            "FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return RoutingDecision(
            decision_id=row[0],
            goal=row[1],
            capability=row[2],
            task=json.loads(row[3] or "{}"),
            selected_provider=row[4],
            candidate_scores=[ScoreBreakdown.from_dict(c) for c in json.loads(row[5] or "[]")],
            excluded_providers=json.loads(row[6] or "[]"),
            timestamp=float(row[7]),
        )

    def get_recent_decisions(self, limit: int = 20) -> list[RoutingDecision]:
        rows = self._conn.execute(
            "SELECT decision_id FROM decisions ORDER BY timestamp DESC, rowid DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        loaded = [self.get_decision(r[0]) for r in rows]
        return [d for d in loaded if d is not None]

    def count_decisions(self, capability: Optional[str] = None) -> int:
        if capability is None:
            row = self._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE capability = ?", (capability,)
            ).fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------ #
    # Outcomes                                                           #
    # ------------------------------------------------------------------ #

    def save_outcome(self, outcome: RoutingOutcome) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO outcomes "
            "(outcome_id, decision_id, success, duration_ms, quality_score, "
            " cost, retries, replan_level, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                outcome.outcome_id,
                outcome.decision_id,
                1 if outcome.success else 0,
                float(outcome.duration_ms),
                float(outcome.quality_score),
                float(outcome.cost),
                int(outcome.retries),
                int(outcome.replan_level),
                float(outcome.timestamp),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _outcome_from_row(row: tuple) -> RoutingOutcome:
        return RoutingOutcome(
            outcome_id=row[0],
            decision_id=row[1],
            success=bool(row[2]),
            duration_ms=float(row[3]),
            quality_score=float(row[4]),
            cost=float(row[5]),
            retries=int(row[6]),
            replan_level=int(row[7]),
            timestamp=float(row[8]),
        )

    _OUTCOME_COLS = (
        "outcome_id, decision_id, success, duration_ms, quality_score, "
        "cost, retries, replan_level, timestamp"
    )

    def get_outcomes_for_decision(self, decision_id: str) -> list[RoutingOutcome]:
        rows = self._conn.execute(
            f"SELECT {self._OUTCOME_COLS} FROM outcomes WHERE decision_id = ? "
            "ORDER BY timestamp ASC",
            (decision_id,),
        ).fetchall()
        return [self._outcome_from_row(r) for r in rows]

    def get_outcomes_with_decisions(
        self,
        provider_id: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> list[tuple[RoutingOutcome, RoutingDecision]]:
        """Outcome/decision pairs (calibrator needs each outcome's task context)."""
        if provider_id is None and capability is None:
            rows = self._conn.execute(
                f"SELECT {', '.join('o.' + c for c in self._OUTCOME_COLS.split(', '))}, "
                "d.decision_id, d.goal, d.capability, d.task, d.selected_provider, "
                "d.candidate_scores, d.excluded_providers, d.timestamp "
                "FROM outcomes o JOIN decisions d ON o.decision_id = d.decision_id "
                "ORDER BY o.timestamp ASC"
            ).fetchall()
        else:
            sql = (
                f"SELECT {', '.join('o.' + c for c in self._OUTCOME_COLS.split(', '))}, "
                "d.decision_id, d.goal, d.capability, d.task, d.selected_provider, "
                "d.candidate_scores, d.excluded_providers, d.timestamp "
                "FROM outcomes o JOIN decisions d ON o.decision_id = d.decision_id WHERE 1=1"
            )
            params: list[Any] = []
            if provider_id is not None:
                sql += " AND d.selected_provider = ?"
                params.append(provider_id)
            if capability is not None:
                sql += " AND d.capability = ?"
                params.append(capability)
            rows = self._conn.execute(sql + " ORDER BY o.timestamp ASC", params).fetchall()
        pairs: list[tuple[RoutingOutcome, RoutingDecision]] = []
        for row in rows:
            outcome = self._outcome_from_row(row[:9])
            decision = RoutingDecision(
                decision_id=row[9], goal=row[10], capability=row[11],
                task=json.loads(row[12] or "{}"), selected_provider=row[13],
                candidate_scores=[ScoreBreakdown.from_dict(c) for c in json.loads(row[14] or "[]")],
                excluded_providers=json.loads(row[15] or "[]"),
                timestamp=float(row[16]),
            )
            pairs.append((outcome, decision))
        return pairs

    def get_all_outcomes(
        self,
        provider_id: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> list[RoutingOutcome]:
        """All outcomes, optionally filtered via join to their decision."""
        if provider_id is None and capability is None:
            rows = self._conn.execute(
                f"SELECT {self._OUTCOME_COLS} FROM outcomes ORDER BY timestamp ASC"
            ).fetchall()
            return [self._outcome_from_row(r) for r in rows]
        sql = (
            f"SELECT o.{', o.'.join(self._OUTCOME_COLS.split(', '))} "
            "FROM outcomes o JOIN decisions d ON o.decision_id = d.decision_id WHERE 1=1"
        )
        params: list[Any] = []
        if provider_id is not None:
            sql += " AND d.selected_provider = ?"
            params.append(provider_id)
        if capability is not None:
            sql += " AND d.capability = ?"
            params.append(capability)
        rows = self._conn.execute(sql + " ORDER BY o.timestamp ASC", params).fetchall()
        return [self._outcome_from_row(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Calibrations                                                       #
    # ------------------------------------------------------------------ #

    def save_calibration(self, entry: CalibrationEntry) -> None:
        """Upsert keyed on the full (provider, capability, context) tuple."""
        self._conn.execute(
            "DELETE FROM calibrations WHERE provider_id = ? AND capability = ? "
            "AND language = ? AND framework = ? AND project_size = ?",
            (entry.provider_id, entry.capability, entry.language,
             entry.framework, entry.project_size),
        )
        self._conn.execute(
            "INSERT INTO calibrations "
            "(entry_id, provider_id, capability, adjustment, confidence, "
            " evidence_count, last_updated, language, framework, project_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.entry_id,
                entry.provider_id,
                entry.capability,
                float(entry.adjustment),
                float(entry.confidence),
                int(entry.evidence_count),
                float(entry.last_updated),
                entry.language,
                entry.framework,
                entry.project_size,
            ),
        )
        self._conn.commit()

    def get_calibration(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> Optional[CalibrationEntry]:
        """Context-EXACT lookup: every given context field must match."""
        row = self._conn.execute(
            "SELECT entry_id, provider_id, capability, adjustment, confidence, "
            "evidence_count, last_updated, language, framework, project_size "
            "FROM calibrations WHERE provider_id = ? AND capability = ? "
            "AND language = ? AND framework = ? AND project_size = ?",
            (provider_id, capability, language, framework, project_size),
        ).fetchone()
        if row is None:
            return None
        return CalibrationEntry(
            entry_id=row[0], provider_id=row[1], capability=row[2],
            adjustment=row[3], confidence=row[4], evidence_count=row[5],
            last_updated=row[6], language=row[7], framework=row[8],
            project_size=row[9],
        )

    def get_calibration_fallback(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> Optional[CalibrationEntry]:
        """Walk _CONTEXT_FALLBACK_CHAIN specific→generic.

        A chain pattern zeroes a dimension only if the stored entry is
        generic (empty) in that dimension; nonzero requires an exact match
        with the requested value.
        """
        requested = (language, framework, project_size)
        for pattern in _CONTEXT_FALLBACK_CHAIN:
            conds = [provider_id, capability]
            for i, keep in enumerate(pattern):
                if keep:
                    conds.append(requested[i])
                else:
                    conds.append("")
            row = self._conn.execute(
                "SELECT entry_id, provider_id, capability, adjustment, confidence, "
                "evidence_count, last_updated, language, framework, project_size "
                "FROM calibrations WHERE provider_id = ? AND capability = ? "
                "AND language = ? AND framework = ? AND project_size = ?",
                conds,
            ).fetchone()
            if row is not None:
                return CalibrationEntry(
                    entry_id=row[0], provider_id=row[1], capability=row[2],
                    adjustment=row[3], confidence=row[4], evidence_count=row[5],
                    last_updated=row[6], language=row[7], framework=row[8],
                    project_size=row[9],
                )
        return None

    def get_all_calibrations(self) -> list[CalibrationEntry]:
        rows = self._conn.execute(
            "SELECT entry_id, provider_id, capability, adjustment, confidence, "
            "evidence_count, last_updated, language, framework, project_size "
            "FROM calibrations"
        ).fetchall()
        return [
            CalibrationEntry(
                entry_id=r[0], provider_id=r[1], capability=r[2],
                adjustment=r[3], confidence=r[4], evidence_count=r[5],
                last_updated=r[6], language=r[7], framework=r[8],
                project_size=r[9],
            )
            for r in rows
        ]

    def get_calibration_summary(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.get_all_calibrations()]

    # ------------------------------------------------------------------ #
    # Stats + maintenance                                                #
    # ------------------------------------------------------------------ #

    def get_provider_stats(self, provider_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT COUNT(*), AVG(o.success), AVG(o.duration_ms), "
            "AVG(o.quality_score), AVG(o.cost) "
            "FROM outcomes o JOIN decisions d ON o.decision_id = d.decision_id "
            "WHERE d.selected_provider = ?",
            (provider_id,),
        ).fetchone()
        total = int(row[0]) if row and row[0] is not None else 0
        if total == 0:
            return {
                "total": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_quality": 0.0,
                "avg_cost": 0.0,
            }
        return {
            "total": total,
            "success_rate": round(float(row[1]), 4),
            "avg_duration_ms": round(float(row[2]), 4),
            "avg_quality": round(float(row[3]), 4),
            "avg_cost": round(float(row[4] or 0.0), 6),
        }

    def clear(self) -> None:
        self._conn.execute("DELETE FROM decisions")
        self._conn.execute("DELETE FROM outcomes")
        self._conn.execute("DELETE FROM calibrations")
        self._conn.commit()
