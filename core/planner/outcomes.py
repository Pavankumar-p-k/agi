"""PlanOutcomeStore — tracks prediction vs actual for plans.

Records predicted metrics at plan creation/execution time and
computes actuals from scheduled activity outcomes after execution.
Enables the accuracy comparison that closes the prediction feedback loop.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.planner.store import PlanStore

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path("data") / "workflow.db")

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plan_outcomes (
    plan_id TEXT PRIMARY KEY,
    predicted_confidence REAL NOT NULL DEFAULT 0.5,
    predicted_success_rate REAL NOT NULL DEFAULT 0.5,
    predicted_duration_days REAL NOT NULL DEFAULT 5,
    predicted_risk_score REAL NOT NULL DEFAULT 0.5,
    predicted_cost TEXT NOT NULL DEFAULT 'medium',

    actual_success INTEGER,
    actual_duration_seconds REAL,
    actual_failures INTEGER,
    actual_cost TEXT,

    executed_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class PlanOutcomeStore:
    """SQLite-backed persistence for plan prediction vs actual outcomes.

    Thread-safe. Each CRUD method opens its own connection.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(_TABLE_SQL)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(
        self, plan_id: str,
        predicted_confidence: float = 0.5,
        predicted_success_rate: float = 0.5,
        predicted_duration_days: float = 5.0,
        predicted_risk_score: float = 0.5,
        predicted_cost: str = "medium",
    ) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO plan_outcomes
                   (plan_id, predicted_confidence, predicted_success_rate,
                    predicted_duration_days, predicted_risk_score, predicted_cost,
                    executed_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (plan_id, predicted_confidence, predicted_success_rate,
                 predicted_duration_days, predicted_risk_score, predicted_cost,
                 now, now, now),
            )
        logger.info("OutcomeStore: created outcome record for plan %s", plan_id)

    def get(self, plan_id: str) -> dict[str, Any] | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM plan_outcomes WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM plan_outcomes ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def record_execution(self, plan_id: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE plan_outcomes SET executed_at = ?, updated_at = ? WHERE plan_id = ?",
                (now, now, plan_id),
            )

    def record_completion(
        self, plan_id: str,
        actual_success: bool,
        actual_duration_seconds: float | None = None,
        actual_failures: int = 0,
        actual_cost: str | None = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE plan_outcomes SET
                   actual_success = ?, actual_duration_seconds = ?,
                   actual_failures = ?, actual_cost = ?,
                   completed_at = ?, updated_at = ?
                   WHERE plan_id = ?""",
                (1 if actual_success else 0, actual_duration_seconds,
                 actual_failures, actual_cost, now, now, plan_id),
            )


# ── Outcome computation ─────────────────────────────────────────────────────


def compute_plan_outcome(plan_id: str) -> dict[str, Any] | None:
    """Compute actual outcome for a plan by querying its scheduled activities.

    Returns enriched outcome dict with prediction vs actual comparison,
    or None if the plan has no outcome record.
    """
    store = PlanOutcomeStore()
    outcome = store.get(plan_id)
    if not outcome:
        return None

    # Gather actuals from scheduled activities
    try:
        from core.scheduler.store import SchedulerStore
        sched = SchedulerStore()
        plan_acts = sched.list_by_metadata("plan_id", plan_id)

        total = len(plan_acts)
        completed = sum(1 for a in plan_acts if a.status == "completed")
        failed = sum(1 for a in plan_acts if a.status in ("failed", "blocked"))
        total_seconds = 0.0
        timed_count = 0

        # Also check activity graph for more precise timing
        try:
            from core.activity.storage import ActivityStore
            act_store = ActivityStore()
            for sa in plan_acts:
                subtree = act_store.get_activity_tree(sa.activity_id)
                for node in subtree:
                    if node.completed_at and node.started_at:
                        dur = (node.completed_at - node.started_at).total_seconds()
                        total_seconds += dur
                        timed_count += 1
        except Exception:
            pass

        actual_success = completed > 0 and failed == 0 if total > 0 else outcome.get("actual_success")
        actual_duration = total_seconds / max(timed_count, 1) if timed_count > 0 else None
        actual_failures = failed

        # Store computed actuals
        store.record_completion(
            plan_id,
            actual_success=bool(actual_success) if total > 0 else bool(outcome.get("actual_success")),
            actual_duration_seconds=round(actual_duration, 1) if actual_duration else None,
            actual_failures=actual_failures,
            actual_cost=outcome.get("predicted_cost"),
        )

        outcome = store.get(plan_id)
    except Exception as e:
        logger.warning("OutcomeStore: failed to compute actuals for %s: %s", plan_id, e)

    return outcome


def get_prediction_accuracy(plan_id: str) -> dict[str, Any] | None:
    """Compare predicted vs actual and return accuracy metrics."""
    outcome = compute_plan_outcome(plan_id)
    if not outcome:
        return None

    accuracy: dict[str, Any] = {
        "plan_id": plan_id,
        "has_actuals": outcome.get("actual_success") is not None,
        "dimensions": {},
        "overall_accuracy": 0.0,
    }

    # 1. Success prediction accuracy
    if outcome.get("actual_success") is not None:
        predicted_success = outcome.get("predicted_confidence", 0.5) >= 0.5
        actual_success = bool(outcome["actual_success"])
        accuracy["dimensions"]["success"] = {
            "predicted": predicted_success,
            "actual": actual_success,
            "correct": predicted_success == actual_success,
            "score": 1.0 if predicted_success == actual_success else 0.0,
        }

    # 2. Duration accuracy
    if outcome.get("actual_duration_seconds") is not None and outcome.get("predicted_duration_days"):
        predicted_days = outcome["predicted_duration_days"]
        actual_hours = outcome["actual_duration_seconds"] / 3600
        actual_days = actual_hours / 8  # 8-hour workdays
        if actual_days > 0:
            ratio = min(predicted_days, actual_days) / max(predicted_days, actual_days)
            accuracy["dimensions"]["duration"] = {
                "predicted_days": predicted_days,
                "actual_days": round(actual_days, 1),
                "actual_seconds": outcome["actual_duration_seconds"],
                "ratio": round(ratio, 3),
                "score": round(ratio, 3),
            }

    # 3. Risk accuracy
    if outcome.get("actual_failures") is not None:
        predicted_risk = outcome.get("predicted_risk_score", 0.5)
        actual_risk = min(1.0, outcome["actual_failures"] / max(outcome.get("predicted_duration_days", 5) * 2, 1))
        risk_diff = abs(predicted_risk - actual_risk)
        accuracy["dimensions"]["risk"] = {
            "predicted": predicted_risk,
            "actual": round(actual_risk, 3),
            "diff": round(risk_diff, 3),
            "score": round(max(0.0, 1.0 - risk_diff), 3),
        }

    # Overall accuracy (average of dimension scores)
    scores = [d["score"] for d in accuracy["dimensions"].values()]
    accuracy["overall_accuracy"] = round(sum(scores) / max(len(scores), 1), 3)

    return accuracy
