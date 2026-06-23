"""PredictionCalibrator — learns from past prediction errors to improve future estimates.

Phase 12.4 closes the loop:
  Prediction → Execution → Actual Outcome → Error → Calibration → Better Prediction

The calibrator stores prediction-vs-actual pairs and computes bias corrections.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import mean, StatisticsError
from typing import Any

from core.belief.integration import BeliefIntegrator
from core.strategy.models import Prediction, Strategy, StrategyDecision

logger = logging.getLogger(__name__)

MIN_EVIDENCE_FOR_CALIBRATION = 3


def _detect_goal_type_domain(goal_type: str) -> str:
    """Map goal_type to a domain for the belief engine."""
    mapping = {
        "build": "build",
        "research": "research",
        "refactor": "coding",
        "explore": "research",
    }
    return mapping.get(goal_type, "general")


@dataclass
class CalibrationRecord:
    """A single prediction vs actual outcome, stored for calibration."""

    decision_id: str
    goal: str
    goal_type: str
    strategy_name: str
    tags: list[str]

    predicted_success: float
    predicted_duration_days: float
    predicted_risk: float

    actual_success: bool
    actual_duration_days: float

    duration_error: float       # (actual - predicted) / predicted
    success_correct: bool       # prediction matched actual outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "goal": self.goal[:60],
            "goal_type": self.goal_type,
            "strategy_name": self.strategy_name,
            "tags": self.tags,
            "predicted_success": self.predicted_success,
            "predicted_duration_days": self.predicted_duration_days,
            "actual_success": self.actual_success,
            "actual_duration_days": self.actual_duration_days,
            "duration_error": round(self.duration_error, 3),
            "success_correct": self.success_correct,
        }


@dataclass
class CalibrationMetrics:
    """Aggregated calibration metrics across multiple records."""

    record_count: int = 0

    duration_bias: float = 0.0      # positive = systematic underestimation
    duration_mape: float = 0.0      # mean absolute percentage error
    duration_std: float | None = None  # variance in estimate quality

    calibration_accuracy: float = 0.0  # how often predictions matched outcomes


class CalibrationStore:
    """Stores CalibrationRecords and computes aggregate metrics.

    In-memory for Phase 12.4. Backed by SQLite in a later phase.
    """

    def __init__(self):
        self._records: list[CalibrationRecord] = []

    def record(self, decision: StrategyDecision, goal_type: str,
               actual_success: bool, actual_duration_days: float) -> CalibrationRecord:
        """Create and store a CalibrationRecord from a completed StrategyDecision."""
        chosen = decision.chosen_strategy
        pred = chosen.prediction

        if pred is None:
            duration_error = 0.0
            predicted_success = 0.5
            predicted_duration = actual_duration_days
            predicted_risk = 0.3
        else:
            predicted_success = pred.success_probability
            predicted_duration = pred.estimated_duration_days
            predicted_risk = pred.estimated_risk
            duration_error = (
                (actual_duration_days - predicted_duration) / predicted_duration
                if predicted_duration > 0 else 0.0
            )

        success_correct = (
            (actual_success and predicted_success >= 0.5)
            or (not actual_success and predicted_success < 0.5)
        )

        record = CalibrationRecord(
            decision_id=decision.decision_id,
            goal=decision.goal,
            goal_type=goal_type,
            strategy_name=chosen.name,
            tags=[t.value for t in chosen.tags],
            predicted_success=round(predicted_success, 3),
            predicted_duration_days=round(predicted_duration, 1),
            predicted_risk=round(predicted_risk, 3),
            actual_success=actual_success,
            actual_duration_days=actual_duration_days,
            duration_error=round(duration_error, 3),
            success_correct=success_correct,
        )

        self._records.append(record)
        return record

    def get_metrics(self, goal_type: str | None = None,
                    tags: list[str] | None = None) -> CalibrationMetrics:
        """Compute aggregate calibration metrics, optionally filtered."""
        records = self._filter(goal_type=goal_type, tags=tags)
        return self._compute_metrics(records)

    def get_all_records(self) -> list[CalibrationRecord]:
        return list(self._records)

    def record_count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()

    def _filter(self, goal_type: str | None = None,
                tags: list[str] | None = None) -> list[CalibrationRecord]:
        filtered = self._records
        if goal_type:
            filtered = [r for r in filtered if r.goal_type == goal_type]
        if tags:
            tag_set = set(tags)
            filtered = [r for r in filtered if tag_set.intersection(r.tags)]
        return filtered

    def _compute_metrics(self, records: list[CalibrationRecord]) -> CalibrationMetrics:
        if not records:
            return CalibrationMetrics()

        metrics = CalibrationMetrics(record_count=len(records))

        duration_errors = [r.duration_error for r in records]
        metrics.duration_bias = round(mean(duration_errors), 3)
        metrics.duration_mape = round(
            mean(abs(e) for e in duration_errors), 3
        )
        if len(duration_errors) >= 2:
            try:
                variance = sum(
                    (e - metrics.duration_bias) ** 2 for e in duration_errors
                ) / (len(duration_errors) - 1)
                metrics.duration_std = round(variance ** 0.5, 3)
            except (StatisticsError, ZeroDivisionError):
                pass

        correct_count = sum(1 for r in records if r.success_correct)
        metrics.calibration_accuracy = round(
            correct_count / len(records), 3
        ) if records else 0.0

        return metrics


class PredictionCalibrator:
    """Adjusts predictions based on historical calibration data.

    Only activates when MIN_EVIDENCE_FOR_CALIBRATION records exist.
    Prefers tag-filtered (narrow) evidence over goal_type-only (broad) evidence.
    """

    def __init__(self, store: CalibrationStore | None = None,
                 belief_integrator: BeliefIntegrator | None = None):
        self.store = store or CalibrationStore()
        self._belief = belief_integrator

    def calibrate(self, prediction: Prediction, goal_type: str,
                  tags: list[str] | None = None) -> Prediction:
        """Adjust a prediction based on historical calibration data.

        Returns a new Prediction with bias-corrected estimates.
        The original is not modified.
        """
        tags = tags or []

        broad = self.store.get_metrics(goal_type=goal_type)
        narrow = self.store.get_metrics(goal_type=goal_type, tags=tags)

        metrics = (
            narrow
            if narrow.record_count >= MIN_EVIDENCE_FOR_CALIBRATION
            else broad
        )

        if metrics.record_count < MIN_EVIDENCE_FOR_CALIBRATION:
            return prediction

        corrected_success = prediction.success_probability
        corrected_duration = prediction.estimated_duration_days
        corrected_risk = prediction.estimated_risk
        corrected_confidence = prediction.confidence

        # Duration correction
        if abs(metrics.duration_bias) > 0.05:
            factor = 1.0 + (metrics.duration_bias * 0.5)
            corrected_duration = max(
                prediction.estimated_duration_days * factor, 0.5
            )

        # Success probability: blend toward 0.5 when calibration is poor
        if (metrics.calibration_accuracy < 0.7
                and metrics.record_count >= MIN_EVIDENCE_FOR_CALIBRATION):
            blend = min(metrics.record_count * 0.1, 0.5)
            corrected_success = (
                prediction.success_probability * (1.0 - blend) + 0.5 * blend
            )

        # Confidence adjustment based on calibration accuracy
        if self._belief is not None:
            corrected_confidence = self._belief.adjust_prediction_confidence(
                domain=goal_type,
                evidence_count=metrics.record_count,
                current_confidence=prediction.confidence,
            )
        elif metrics.calibration_accuracy > 0.8:
            corrected_confidence = min(prediction.confidence + 0.1, 0.95)
        elif metrics.calibration_accuracy < 0.6:
            corrected_confidence = max(prediction.confidence - 0.1, 0.05)
        else:
            corrected_confidence = prediction.confidence

        # Risk increase when duration variance is high
        if metrics.duration_std is not None and metrics.duration_std > 0.3:
            corrected_risk = min(prediction.estimated_risk * 1.2, 1.0)

        return Prediction(
            success_probability=round(corrected_success, 3),
            estimated_duration_days=round(corrected_duration, 1),
            estimated_risk=round(corrected_risk, 3),
            estimated_effort=prediction.estimated_effort,
            confidence=round(corrected_confidence, 3),
            evidence_count=prediction.evidence_count,
        )

    def record_outcome(self, decision: StrategyDecision, goal_type: str = "build",
                       actual_success: bool | None = None,
                       actual_duration_days: float | None = None
                       ) -> CalibrationRecord | None:
        """Record the actual outcome of a completed strategy decision."""
        success = (
            actual_success
            if actual_success is not None
            else decision.actual_success
        )
        duration = (
            actual_duration_days
            if actual_duration_days is not None
            else decision.actual_duration_days
        )

        if success is None or duration is None:
            logger.warning(
                "PredictionCalibrator: incomplete outcome data for %s",
                decision.decision_id,
            )
            return None

        record = self.store.record(decision, goal_type, success, duration)

        # Phase 16.1: Feed accuracy outcome to Belief Quality Engine
        if self._belief is not None and decision.chosen_strategy.prediction is not None:
            pred = decision.chosen_strategy.prediction
            domain = _detect_goal_type_domain(goal_type)
            self._belief.record_prediction_accuracy(
                belief_id=decision.decision_id,
                domain=domain,
                category="heuristic",
                predicted_value=pred.success_probability,
                actual_value=1.0 if success else 0.0,
            )

        return record

    def recalibrate(self, decision: StrategyDecision, goal_type: str,
                    actual_success: bool, actual_duration_days: float
                    ) -> Prediction | None:
        """Record an outcome and return the recalibrated prediction for review."""
        self.record_outcome(decision, goal_type, actual_success, actual_duration_days)
        chosen = decision.chosen_strategy
        if chosen.prediction is None:
            return None
        tags = [t.value for t in chosen.tags]
        return self.calibrate(chosen.prediction, goal_type, tags)
