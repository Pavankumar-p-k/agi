"""ExperimentRunner — A/B test framework for behavior changes.

Each experiment:
  1. Takes a snapshot of current knob values (control arm)
  2. Applies candidate knob changes (candidate arm)
  3. Runs a configurable number of workflows in each arm
  4. Records metrics for both arms
  5. Returns results for evaluation

Experiments are stored in workflow.db for durability.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.improvement.knob_store import KnobStore
from core.improvement.models import (
    DEFAULT_KNOBS_JSON,
    Experiment,
    ExperimentResult,
    ExperimentStatus,
    KnobChange,
    MetricComparison,
)
from core.long_term_memory.models import UNIFIED_DB

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Creates and manages A/B experiments on behavior knobs.

    Usage:
        runner = ExperimentRunner(knob_store)
        exp = runner.create_experiment(proposal_id, changes)
        runner.start_experiment(exp.experiment_id)
        # ... run workflows ...
        result = runner.complete_experiment(exp.experiment_id, control, candidate)
    """

    def __init__(self, knob_store: KnobStore | None = None,
                 db_path: str | None = None):
        self._knob_store = knob_store or KnobStore()
        self._db_path = db_path or UNIFIED_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    knob_changes_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PLANNED',
                    start_time TEXT,
                    end_time TEXT,
                    control_metrics_json TEXT DEFAULT '{}',
                    candidate_metrics_json TEXT DEFAULT '{}'
                );
            """)

    def create_experiment(self, proposal_id: str,
                          changes: list[KnobChange]) -> Experiment:
        exp_id = f"exp_{uuid.uuid4().hex[:12]}"
        exp = Experiment(
            experiment_id=exp_id,
            proposal_id=proposal_id,
            knob_changes=changes,
            status=ExperimentStatus.PLANNED,
        )
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO experiments
                   (experiment_id, proposal_id, knob_changes_json, status)
                   VALUES (?, ?, ?, ?)""",
                (exp_id, proposal_id,
                 json.dumps([c.__dict__ for c in changes]),
                 ExperimentStatus.PLANNED.value),
            )
        logger.info("ExperimentRunner: created %s with %d changes",
                     exp_id, len(changes))
        return exp

    def start_experiment(self, experiment_id: str) -> bool:
        """Start the experiment by applying candidate changes.

        Returns True if started successfully.
        """
        exp = self._get_experiment(experiment_id)
        if exp is None or exp.status != ExperimentStatus.PLANNED:
            return False

        # 1. Snapshot current values for rollback
        self._last_snapshot = self._knob_store.get_snapshot()

        # 2. Apply candidate changes
        for change in exp.knob_changes:
            self._knob_store.set(change.knob_name, change.new_value)

        now = datetime.utcnow()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE experiments SET status=?, start_time=? WHERE experiment_id=?",
                (ExperimentStatus.RUNNING.value, now.isoformat(), experiment_id),
            )
        exp.status = ExperimentStatus.RUNNING
        exp.start_time = now
        logger.info("ExperimentRunner: started %s", experiment_id)
        return True

    def complete_experiment(self, experiment_id: str,
                            control_metrics: dict[str, float],
                            candidate_metrics: dict[str, float]) -> ExperimentResult | None:
        """Complete the experiment, rollback candidate changes,
        and return the comparison result.

        The candidate changes are ALWAYS rolled back after measurement.
        If the result is positive, SafePromotion will re-apply them.
        """
        exp = self._get_experiment(experiment_id)
        if exp is None or exp.status != ExperimentStatus.RUNNING:
            return None

        now = datetime.utcnow()
        exp.control_metrics = control_metrics
        exp.candidate_metrics = candidate_metrics
        exp.end_time = now
        exp.status = ExperimentStatus.COMPLETED

        # Persist metrics
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE experiments SET status=?, end_time=?,
                   control_metrics_json=?, candidate_metrics_json=?
                   WHERE experiment_id=?""",
                (ExperimentStatus.COMPLETED.value, now.isoformat(),
                 json.dumps(control_metrics), json.dumps(candidate_metrics),
                 experiment_id),
            )

        # Rollback candidate changes
        if hasattr(self, "_last_snapshot"):
            self._knob_store.apply_snapshot(self._last_snapshot)

        # Build comparison
        comparisons = self._build_comparisons(control_metrics, candidate_metrics)
        overall = self._compute_overall(comparisons)
        summary = self._format_summary(comparisons, overall)

        logger.info("ExperimentRunner: completed %s — overall=%s",
                     experiment_id, overall)
        return ExperimentResult(
            experiment_id=experiment_id,
            metric_comparisons=comparisons,
            overall_improvement=overall,
            summary=summary,
        )

    def _build_comparisons(self, control: dict[str, float],
                            candidate: dict[str, float]) -> list[MetricComparison]:
        comparisons: list[MetricComparison] = []
        all_keys = set(control.keys()) | set(candidate.keys())
        for key in sorted(all_keys):
            c_val = control.get(key, 0.0)
            cand_val = candidate.get(key, 0.0)
            delta = cand_val - c_val
            # For success_rate, higher is better. For error_rate, lower is better.
            improvement = self._is_improvement(key, delta)
            comparisons.append(MetricComparison(
                metric_name=key,
                control_mean=c_val,
                candidate_mean=cand_val,
                delta=delta,
                improvement=improvement,
            ))
        return comparisons

    @staticmethod
    def _is_improvement(metric: str, delta: float) -> bool:
        """Higher is improvement for success_rate, lower for error_rate, completion_time."""
        if "error" in metric.lower() or "time" in metric.lower():
            return delta < 0
        return delta > 0

    @staticmethod
    def _compute_overall(comparisons: list[MetricComparison]) -> bool:
        if not comparisons:
            return False
        improved = sum(1 for c in comparisons if c.improvement)
        return improved > len(comparisons) / 2

    @staticmethod
    def _format_summary(comparisons: list[MetricComparison],
                         overall: bool) -> str:
        parts = [f"Overall: {'IMPROVED' if overall else 'NOT IMPROVED'}"]
        for c in comparisons:
            arrow = "+" if c.delta >= 0 else ""
            parts.append(f"  {c.metric_name}: {c.control_mean:.3f} → {c.candidate_mean:.3f} ({arrow}{c.delta:.3f})")
        return "\n".join(parts)

    def get_experiments(self, limit: int = 20) -> list[Experiment]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY start_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_experiment(r) for r in rows]

    def _get_experiment(self, experiment_id: str) -> Experiment | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id=?",
                (experiment_id,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_experiment(row)


def _row_to_experiment(row: sqlite3.Row) -> Experiment:
    changes_data = json.loads(row["knob_changes_json"])
    changes = [KnobChange(**c) for c in changes_data]
    return Experiment(
        experiment_id=row["experiment_id"],
        proposal_id=row["proposal_id"],
        knob_changes=changes,
        status=ExperimentStatus(row["status"]),
        start_time=_parse_dt(row["start_time"]),
        end_time=_parse_dt(row["end_time"]),
        control_metrics=json.loads(row["control_metrics_json"] or "{}"),
        candidate_metrics=json.loads(row["candidate_metrics_json"] or "{}"),
    )


def _parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None
