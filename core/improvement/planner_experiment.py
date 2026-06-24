"""PlannerExperimentManager — runs controlled experiments on planner configuration.

Experiments test changes to strategy weights, confidence formula parameters,
or ranking configuration and measure the effect on planner performance.
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

from core.analytics.planner import PlannerAnalytics
from core.improvement.knob_store import KnobStore
from core.improvement.models import KnobCategory

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path("data") / "workflow.db")

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS planner_experiments (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    config_before TEXT,
    config_after TEXT,
    metrics_before TEXT,
    metrics_after TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT
);
"""


class PlannerExperimentManager:
    """Creates and manages planner-specific A/B experiments.

    Each experiment:
      1. Records planner performance before the change (control)
      2. Applies the experimental change (strategy weight, config tweak)
      3. Waits for measurement (new plans executed under new config)
      4. Records performance after
      5. Computes whether the change improved things
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(_TABLE_SQL)
            # Migration: add updated_at if missing
            try:
                conn.execute("ALTER TABLE planner_experiments ADD COLUMN updated_at TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

    # ── CRUD ───────────────────────────────────────────────────────────────

    def create(self, opportunity: dict, knob_store: KnobStore | None = None) -> dict[str, Any]:
        """Create an experiment from an improvement opportunity."""
        ks = knob_store or KnobStore()
        exp_id = f"exp_{uuid.uuid4().hex[:12]}"

        # Snapshot current config
        config_before = self._snapshot_planner_config(ks)
        metrics_before = PlannerAnalytics().compute()

        title = f"Experiment: {opportunity.get('recommended_change', opportunity['description'][:60])}"
        now = datetime.utcnow().isoformat()

        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO planner_experiments
                   (id, opportunity_id, title, description, type, status,
                    config_before, metrics_before, created_at)
                   VALUES (?, ?, ?, ?, ?, 'created', ?, ?, ?)""",
                (exp_id, opportunity.get("id", ""), title,
                 opportunity["description"][:200],
                 opportunity.get("type", "strategy_tuning"),
                 json.dumps(config_before),
                 json.dumps({
                     "overall_accuracy": metrics_before.get("overall", {}).get("avg_prediction_accuracy"),
                     "success_rate": metrics_before.get("overall", {}).get("success_rate"),
                     "strategy_win_rates": metrics_before.get("strategy_win_rates", []),
                     "calibration_error": metrics_before.get("confidence_calibration", {}).get("avg_calibration_error"),
                 }),
                 now),
            )

        return self.get(exp_id)

    def get(self, exp_id: str) -> dict[str, Any] | None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM planner_experiments WHERE id = ?", (exp_id,)
            ).fetchone()
        if not row:
            return None
        return self._decode_row(dict(row))

    def list_all(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM planner_experiments WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM planner_experiments ORDER BY created_at DESC"
                ).fetchall()
        return [self._decode_row(dict(r)) for r in rows]

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self, exp_id: str, knob_store: KnobStore | None = None) -> dict[str, Any] | None:
        """Start the experiment by applying the change to knob store."""
        ks = knob_store or KnobStore()
        exp = self.get(exp_id)
        if not exp or exp["status"] != "created":
            return exp

        # Build config change from opportunity type
        opp_id = exp.get("opportunity_id", "")
        config_after = self._build_experiment_config(exp, opp_id, ks)

        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE planner_experiments
                   SET status = 'running', config_after = ?, started_at = ?, updated_at = ?
                   WHERE id = ?""",
                (json.dumps(config_after), now, now, exp_id),
            )

        return self.get(exp_id)

    def complete(self, exp_id: str, knob_store: KnobStore | None = None) -> dict | None:
        """Complete the experiment: measure results and roll back."""
        ks = knob_store or KnobStore()
        exp = self.get(exp_id)
        if not exp or exp["status"] != "running":
            return exp

        # Measure results
        metrics_after = PlannerAnalytics().compute()

        # Compare with before
        metrics_before = exp.get("metrics_before", {})
        result = self._compute_result(metrics_before, metrics_after)

        # Roll back config
        config_before = exp.get("config_before", {})
        self._restore_config(config_before, ks)

        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """UPDATE planner_experiments
                   SET status = 'completed', metrics_after = ?, result = ?,
                       completed_at = ?, updated_at = ?
                   WHERE id = ?""",
                (json.dumps({
                    "overall_accuracy": metrics_after.get("overall", {}).get("avg_prediction_accuracy"),
                    "success_rate": metrics_after.get("overall", {}).get("success_rate"),
                    "strategy_win_rates": metrics_after.get("strategy_win_rates", []),
                    "calibration_error": metrics_after.get("confidence_calibration", {}).get("avg_calibration_error"),
                }), json.dumps(result), now, now, exp_id),
            )

        result["experiment_id"] = exp_id
        return result

    def promote(self, exp_id: str, knob_store: KnobStore | None = None) -> dict[str, Any] | None:
        """Mark an experiment as promoted (config change is kept)."""
        exp = self.get(exp_id)
        if not exp:
            return None

        config_after = exp.get("config_after", {})
        if config_after:
            ks = knob_store or KnobStore()
            self._restore_config(config_after, ks)

        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE planner_experiments SET status = 'promoted', updated_at = ? WHERE id = ?",
                (now, exp_id),
            )
        return self.get(exp_id)

    def rollback(self, exp_id: str, knob_store: KnobStore | None = None) -> dict[str, Any] | None:
        """Roll back an experiment (restore original config)."""
        exp = self.get(exp_id)
        if not exp:
            return None

        config_before = exp.get("config_before", {})
        if config_before:
            ks = knob_store or KnobStore()
            self._restore_config(config_before, ks)

        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE planner_experiments SET status = 'rolled_back', updated_at = ? WHERE id = ?",
                (now, exp_id),
            )
        return self.get(exp_id)

    # ── Internals ──────────────────────────────────────────────────────────

    def _snapshot_planner_config(self, knob_store: KnobStore) -> dict[str, Any]:
        """Snapshot all planner-related knobs."""
        snapshot = knob_store.get_snapshot()
        return {k: v for k, v in snapshot.items() if k.startswith("planner.")}

    def _restore_config(self, config: dict[str, Any], knob_store: KnobStore) -> None:
        """Restore planner config from a snapshot."""
        for name, value in config.items():
            knob_store.set(name, value)

    def _build_experiment_config(
        self, exp: dict, opp_id: str, knob_store: KnobStore
    ) -> dict[str, Any]:
        """Build the experimental config change based on the opportunity type."""
        exp_type = exp.get("type", "strategy_tuning")
        config_after = self._snapshot_planner_config(knob_store)

        if opp_id:
            from core.improvement.planner_detector import PlannerImprovementDetector
            detector = PlannerImprovementDetector()
            all_opps = detector.detect_all()
            opp = next((o for o in all_opps if o["id"] == opp_id), None)
        else:
            opp = None

        if exp_type == "strategy_tuning" and opp:
            strat = opp.get("strategy", "")
            knob_name = f"planner.strategy_weight.{strat}"
            if knob_name in KNOB_NAMES:
                current = knob_store.get(knob_name) or 1.0
                new_val = max(0.1, current * 0.5)  # halve the weight
                knob_store.set(knob_name, new_val)
                config_after[knob_name] = new_val
            else:
                logger.info("No knob for strategy '%s', skipping strategy_tuning", strat)
                # Apply a default mitigation: disable planner.inject_domain_patterns
                knob_store.set("planner.inject_domain_patterns", False)
                config_after["planner.inject_domain_patterns"] = False

        elif exp_type == "calibration_adjustment":
            for name in KNOB_NAMES:
                current = knob_store.get(name) or 1.0
                if current < 1.0:
                    # If a strategy is already suppressed, boost it
                    new_val = min(1.0, current * 1.5)
                    knob_store.set(name, new_val)
                    config_after[name] = new_val

        elif exp_type == "risk_reweighting":
            for name in ["planner.inject_domain_patterns", "planner.inject_failure_warnings"]:
                current = knob_store.get(name)
                knob_store.set(name, not current)
                config_after[name] = not current

        return config_after

    @staticmethod
    def _compute_result(before: dict, after: dict) -> dict:
        """Compare metrics before and after to determine improvement."""
        before_acc = before.get("overall_accuracy") if isinstance(before.get("overall_accuracy"), (int, float)) else None
        after_acc = after.get("overall_accuracy") if isinstance(after.get("overall_accuracy"), (int, float)) else None
        before_sr = before.get("success_rate") if isinstance(before.get("success_rate"), (int, float)) else None
        after_sr = after.get("success_rate") if isinstance(after.get("success_rate"), (int, float)) else None

        changes = {}
        improved = True

        if before_acc is not None and after_acc is not None:
            acc_change = after_acc - before_acc
            changes["accuracy_change"] = round(acc_change, 3)
            if acc_change < -0.02:
                improved = False

        if before_sr is not None and after_sr is not None:
            sr_change = after_sr - before_sr
            changes["success_rate_change"] = round(sr_change, 3)
            if sr_change < -0.02:
                improved = False

        overall = "improved" if improved else "regressed"
        if not changes:
            overall = "insufficient_data"

        return {
            "overall": overall,
            "changes": changes,
            "improved": improved,
        }

    @staticmethod
    def _decode_row(row: dict) -> dict:
        for key in ("config_before", "config_after", "metrics_before", "metrics_after", "result"):
            if isinstance(row.get(key), str):
                try:
                    row[key] = json.loads(row[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return row


KNOB_NAMES = [
    "planner.strategy_weight.flutter",
    "planner.strategy_weight.native_android",
    "planner.strategy_weight.react_native",
    "planner.strategy_weight.web_pwa",
    "planner.strategy_weight.ios_native",
    "planner.strategy_weight.backend_first",
]
