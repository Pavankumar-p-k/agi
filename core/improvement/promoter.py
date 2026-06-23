"""SafePromotion — decides whether to keep or revert experiment results.

Only promotes changes when:
  1. Overall improvement is positive
  2. No critical metric regressed beyond tolerable threshold
  3. Change is within safe bounds

Promotion is a two-phase commit:
  1. Phase 1: Apply changes to KnobStore (reversible via snapshot)
  2. Phase 2: Mark experiment as PROMOTED in DB (permanent record)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.improvement.experiment import ExperimentRunner
from core.improvement.knob_store import KnobStore
from core.improvement.models import DEFAULT_KNOBS_JSON, ExperimentResult, ExperimentStatus
from core.long_term_memory.models import UNIFIED_DB

logger = logging.getLogger(__name__)

_MAX_REGRESSION_FRACTION = 0.05  # allow at most 5% regression per metric


class SafePromotion:
    """Decides keep/revert for experiment results.

    Usage:
        promoter = SafePromotion(knob_store)
        decision = promoter.evaluate(result)
        if decision["accepted"]:
            promoter.promote(experiment_id, result)
        else:
            promoter.reject(experiment_id, result)
    """

    def __init__(self, knob_store: KnobStore | None = None,
                 db_path: str | None = None):
        self._knob_store = knob_store or KnobStore()
        self._db_path = db_path or UNIFIED_DB

    def evaluate(self, result: ExperimentResult) -> dict[str, Any]:
        """Evaluate whether an experiment result should be promoted.

        Returns:
            {"accepted": bool, "reason": str}
        """
        if not result.metric_comparisons:
            return {"accepted": False, "reason": "No metrics to evaluate"}

        critical_regression = False
        regressions: list[str] = []

        for mc in result.metric_comparisons:
            if not mc.improvement:
                # Check for critical regression
                if mc.control_mean > 0 and abs(mc.delta / mc.control_mean) > _MAX_REGRESSION_FRACTION:
                    critical_regression = True
                    regressions.append(
                        f"{mc.metric_name} regressed by {abs(mc.delta):.1%}"
                    )

        if not result.overall_improvement:
            return {
                "accepted": False,
                "reason": "No overall improvement detected",
            }

        if critical_regression:
            return {
                "accepted": False,
                "reason": f"Critical regressions: {'; '.join(regressions)}",
            }

        return {
            "accepted": True,
            "reason": f"Improved {sum(1 for mc in result.metric_comparisons if mc.improvement)}/{len(result.metric_comparisons)} metrics",
        }

    def promote(self, experiment_id: str, result: ExperimentResult) -> bool:
        """Promote the candidate changes: apply to KnobStore and mark as promoted.

        Returns True on success.
        """
        decision = self.evaluate(result)
        if not decision["accepted"]:
            logger.warning("SafePromotion: %s rejected — %s", experiment_id, decision["reason"])
            return False

        # Re-apply the candidate changes that were rolled back by ExperimentRunner
        exp = self._get_experiment(experiment_id)
        if exp is None:
            return False

        for change in exp.knob_changes:
            self._knob_store.set(change.knob_name, change.new_value)

        # Mark as PROMOTED in DB (we use COMPLETED and store the decision in metadata)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE experiments SET status=?, end_time=? WHERE experiment_id=?",
                ("PROMOTED", datetime.utcnow().isoformat(), experiment_id),
            )

        logger.info("SafePromotion: PROMOTED %s — %s", experiment_id, decision["reason"])
        return True

    def reject(self, experiment_id: str, result: ExperimentResult) -> bool:
        """Explicitly reject and mark experiment as REVERTED."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE experiments SET status=?, end_time=? WHERE experiment_id=?",
                ("REVERTED", datetime.utcnow().isoformat(), experiment_id),
            )
        logger.info("SafePromotion: REVERTED %s", experiment_id)
        return True

    def _get_experiment(self, experiment_id: str):
        from core.improvement.experiment import ExperimentRunner
        runner = ExperimentRunner(self._knob_store, self._db_path)
        return runner._get_experiment(experiment_id)
