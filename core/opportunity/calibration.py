"""OpportunityCalibrator — adjusts opportunity scores based on historical prediction accuracy.

The calibrator provides the feedback loop:

    Predict → Execute → Measure → Learn → Improve

For each discovery source, it tracks:

    Mean Error       — systematic over/under-estimation
    MAPE             — mean absolute percentage error
    Source Accuracy  — 1 - min(1.0, MAPE)
    Bias             — positive = overestimation, negative = underestimation

The adjustment factor is applied as a 5th dimension in the opportunity formula:

    opportunity_score = impact × headroom × success_probability × confidence × calibration_accuracy
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from core.opportunity.store import OpportunityRecord, OpportunityStore

logger = logging.getLogger(__name__)

# Minimum records before calibration kicks in
MIN_RECORDS_FOR_CALIBRATION = 3

# Default adjustment when no data is available (neutral)
DEFAULT_ADJUSTMENT = 1.0

# Maximum downward adjustment (prevent complete suppression)
MAX_DOWNWARD_ADJUST = 0.10

# Maximum upward adjustment (prevent unbounded optimism)
MAX_UPWARD_ADJUST = 1.10


class OpportunityCalibrator:
    """Tracks prediction accuracy per source and produces adjustment factors.

    Stateless — all state lives in the injected OpportunityStore.
    """

    def __init__(self, store: OpportunityStore | None = None):
        self.store = store or OpportunityStore()

    # ── Recording ──────────────────────────────────────────────────────

    def record_outcome(
        self,
        opportunity_id: str,
        source: str,
        target_system: str,
        predicted_score: float,
        actual_improvement: float,
        actual_success: bool,
    ) -> OpportunityRecord:
        """Record the outcome of a selected opportunity.

        Args:
            opportunity_id: unique ID of the opportunity
            source: discovery source (bottleneck/ceiling/experiment/principle)
            target_system: which system was improved
            predicted_score: the original opportunity_score from the engine
            actual_improvement: measured improvement after execution (0.0–1.0)
            actual_success: whether the improvement was deemed successful

        Returns:
            The recorded OpportunityRecord.
        """
        record = OpportunityRecord(
            opportunity_id=opportunity_id,
            source=source,
            target_system=target_system,
            predicted_score=predicted_score,
            actual_improvement=actual_improvement,
            actual_success=actual_success,
            selected_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save(record)
        return record

    def record_outcome_from_result(
        self,
        opportunity_id: str,
        source: str,
        target_system: str,
        predicted_score: float,
        result: dict[str, Any] | None = None,
    ) -> OpportunityRecord:
        """Record outcome from a result dict (e.g. from StrategyExecutor).

        Expected result keys:
            overall_improvement: bool
            improvement_score: float (0.0–1.0)
        """
        if result is None:
            result = {}
        actual_success = result.get("overall_improvement", False)
        actual_improvement = result.get("improvement_score", 0.5 if actual_success else 0.0)
        return self.record_outcome(
            opportunity_id=opportunity_id,
            source=source,
            target_system=target_system,
            predicted_score=predicted_score,
            actual_improvement=actual_improvement,
            actual_success=actual_success,
        )

    # ── Metrics ────────────────────────────────────────────────────────

    def get_metrics(
        self,
        source: str | None = None,
        target_system: str | None = None,
    ) -> dict[str, Any]:
        """Get calibration metrics, optionally filtered by source or system.

        Returns:
            dict with keys: count, mean_error, mape, source_accuracy, bias
        """
        records = self.store.list_records(
            source=source,
            target_system=target_system,
            limit=1000,
        )

        if not records:
            return {
                "count": 0,
                "mean_error": 0.0,
                "mape": 0.0,
                "source_accuracy": 1.0,
                "bias": 0.0,
            }

        total_error = sum(r.prediction_error for r in records)
        abs_percent_errors = []
        for r in records:
            actual = abs(r.actual_improvement) if r.actual_improvement else 0.01
            ape = abs(r.prediction_error) / actual
            abs_percent_errors.append(min(ape, 2.0))  # cap at 200%

        count = len(records)
        mean_error = total_error / count
        mape = sum(abs_percent_errors) / count if abs_percent_errors else 0.0
        source_accuracy = max(0.0, 1.0 - mape)

        # Bias: positive → overestimation, negative → underestimation
        bias = mean_error

        return {
            "count": count,
            "mean_error": round(mean_error, 3),
            "mape": round(mape, 3),
            "source_accuracy": round(source_accuracy, 3),
            "bias": round(bias, 3),
        }

    def get_overall_accuracy(self) -> float:
        """Weighted average accuracy across all sources."""
        metrics = self.get_metrics()
        if metrics["count"] < MIN_RECORDS_FOR_CALIBRATION:
            return 1.0
        return metrics["source_accuracy"]

    def get_source_accuracy(self, source: str) -> float:
        """Per-source accuracy score."""
        metrics = self.get_metrics(source=source)
        if metrics["count"] < MIN_RECORDS_FOR_CALIBRATION:
            return 1.0  # no data → neutral
        return metrics["source_accuracy"]

    # ── Adjustment ─────────────────────────────────────────────────────

    def get_adjustment_factor(
        self,
        source: str | None = None,
        target_system: str | None = None,
    ) -> float:
        """Compute a multiplicative factor to adjust opportunity scores.

        The factor is based on historical source_accuracy for the given
        source and/or target_system. Falls back to broader aggregations
        when specific data is insufficient.

        Returns:
            0.0–1.10 where:
              - 1.0 = neutral (no data or perfect accuracy)
              - < 1.0 = historical overestimation
              - > 1.0 = historical underestimation (rare, capped at 1.10)
        """
        # Try most specific: source + target_system
        if source and target_system:
            metrics = self.get_metrics(source=source, target_system=target_system)
            if metrics["count"] >= MIN_RECORDS_FOR_CALIBRATION:
                return self._bias_to_factor(metrics["bias"], metrics["source_accuracy"])

        # Try source-only
        if source:
            metrics = self.get_metrics(source=source)
            if metrics["count"] >= MIN_RECORDS_FOR_CALIBRATION:
                return self._bias_to_factor(metrics["bias"], metrics["source_accuracy"])

        # Try target_system-only
        if target_system:
            metrics = self.get_metrics(target_system=target_system)
            if metrics["count"] >= MIN_RECORDS_FOR_CALIBRATION:
                return self._bias_to_factor(metrics["bias"], metrics["source_accuracy"])

        # Fall back to global
        metrics = self.get_metrics()
        if metrics["count"] >= MIN_RECORDS_FOR_CALIBRATION:
            return self._bias_to_factor(metrics["bias"], metrics["source_accuracy"])

        return DEFAULT_ADJUSTMENT

    def list_source_accuracies(self) -> dict[str, float]:
        """Return accuracy for every source that has data."""
        records = self.store.list_records(limit=10000)
        source_counts: dict[str, list[float]] = {}
        for r in records:
            if r.source not in source_counts:
                source_counts[r.source] = []
            source_counts[r.source].append(abs(r.prediction_error))

        result: dict[str, float] = {}
        for source_name, errors in source_counts.items():
            if len(errors) >= MIN_RECORDS_FOR_CALIBRATION:
                mape = sum(min(e / 0.01, 2.0) for e in errors) / len(errors)
                result[source_name] = round(max(0.0, 1.0 - mape), 3)
        return result

    # ── Internal ───────────────────────────────────────────────────────

    def _bias_to_factor(self, bias: float, accuracy: float) -> float:
        """Convert bias + accuracy into a multiplicative adjustment factor.

        Positive bias (overestimation) → reduce scores.
        Negative bias (underestimation) → increase scores slightly.

        The adjustment is proportional to both the bias magnitude and
        the historical accuracy (high-accuracy predictions adjust less).
        """
        # Scale: if accuracy is high, trust the bias more
        # If accuracy is low, be conservative with adjustment
        trust_weight = accuracy  # 0.0–1.0

        # Bias adjustment: bring scores toward actuals
        # A 0.20 overestimation bias at 0.80 accuracy → reduce by 0.16
        adjustment = 1.0 - (bias * trust_weight)

        return max(MAX_DOWNWARD_ADJUST, min(MAX_UPWARD_ADJUST, adjustment))
