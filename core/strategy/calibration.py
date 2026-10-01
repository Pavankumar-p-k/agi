"""Prediction calibration from historical outcomes (Phase 12.4)."""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional

from core.strategy.models import Prediction, StrategyDecision

MIN_EVIDENCE_FOR_CALIBRATION = 3
_RISK_STD_THRESHOLD = 0.3


def _tag_value(tag) -> str:
    return getattr(tag, "value", tag)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class CalibrationRecord:
    """A single realised outcome matched to a prediction."""

    decision_id: str
    goal: str = ""
    goal_type: str = ""
    strategy_name: str = ""
    tags: List[str] = field(default_factory=list)
    predicted_success: float = 0.0
    predicted_duration_days: float = 0.0
    predicted_risk: float = 0.0
    actual_success: bool = False
    actual_duration_days: float = 0.0
    duration_error: float = 0.0
    success_correct: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationMetrics:
    """Aggregate calibration statistics for a slice of records."""

    record_count: int = 0
    duration_bias: float = 0.0
    duration_std: Optional[float] = None
    calibration_accuracy: float = 0.0


class CalibrationStore:
    """Store calibration records and compute metrics over them."""

    def __init__(self) -> None:
        self._records: List[CalibrationRecord] = []

    def record(
        self,
        decision: StrategyDecision,
        goal_type: str,
        actual_success: bool,
        actual_duration_days: float,
    ) -> CalibrationRecord:
        strategy = decision.chosen_strategy
        prediction = strategy.prediction if strategy else None

        if prediction is not None:
            predicted_duration = prediction.estimated_duration_days
            if predicted_duration:
                duration_error = (
                    actual_duration_days - predicted_duration
                ) / predicted_duration
            else:
                duration_error = 0.0
            predicted_success = prediction.success_probability
            predicted_risk = prediction.estimated_risk
        else:
            predicted_duration = 0.0
            duration_error = 0.0
            predicted_success = 0.0
            predicted_risk = 0.0

        success_correct = (predicted_success >= 0.5) == bool(actual_success)

        tags = [_tag_value(t) for t in (strategy.tags if strategy else [])]
        record = CalibrationRecord(
            decision_id=decision.decision_id,
            goal=decision.goal,
            goal_type=goal_type,
            strategy_name=strategy.name if strategy else "",
            tags=tags,
            predicted_success=predicted_success,
            predicted_duration_days=predicted_duration,
            predicted_risk=predicted_risk,
            actual_success=bool(actual_success),
            actual_duration_days=actual_duration_days,
            duration_error=duration_error,
            success_correct=success_correct,
        )
        self._records.append(record)
        return record

    def record_count(self) -> int:
        return len(self._records)

    def get_records(self) -> List[CalibrationRecord]:
        return list(self._records)

    def get_metrics(
        self,
        goal_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> CalibrationMetrics:
        records = list(self._records)
        if goal_type is not None:
            records = [r for r in records if r.goal_type == goal_type]
        if tags:
            wanted = {_tag_value(t) for t in tags}
            records = [r for r in records if wanted & set(r.tags)]

        if not records:
            return CalibrationMetrics()

        errors = [r.duration_error for r in records]
        accuracy = sum(1 for r in records if r.success_correct) / len(records)
        std = statistics.pstdev(errors) if len(errors) > 1 else None
        return CalibrationMetrics(
            record_count=len(records),
            duration_bias=statistics.mean(errors),
            duration_std=std,
            calibration_accuracy=accuracy,
        )

    def clear(self) -> None:
        self._records = []


class PredictionCalibrator:
    """Adjust predictions using historical calibration data."""

    def __init__(self, store: Optional[CalibrationStore] = None,
                 belief_integrator=None) -> None:
        self.store = store or CalibrationStore()
        self.belief_integrator = belief_integrator

    # ── metric selection ─────────────────────────────────────────────

    def _select_metrics(
        self, goal_type: str, tags: Optional[List[str]]
    ) -> Optional[CalibrationMetrics]:
        tags = tags or []
        if tags:
            narrow = self.store.get_metrics(goal_type=goal_type, tags=tags)
            if narrow.record_count >= MIN_EVIDENCE_FOR_CALIBRATION:
                return narrow
        broad = self.store.get_metrics(goal_type=goal_type)
        if broad.record_count >= MIN_EVIDENCE_FOR_CALIBRATION:
            return broad
        return None

    # ── calibration ──────────────────────────────────────────────────

    def calibrate(
        self,
        prediction: Prediction,
        goal_type: str = "build",
        tags: Optional[List[str]] = None,
    ) -> Prediction:
        metrics = self._select_metrics(goal_type, tags)
        if metrics is None:
            return prediction.copy()

        correction = 1.0 + metrics.duration_bias * 0.5
        duration = prediction.estimated_duration_days * correction

        blend = min(metrics.record_count * 0.1, 0.5)
        success = prediction.success_probability * (1 - blend) + 0.5 * blend

        accuracy = metrics.calibration_accuracy
        confidence = prediction.confidence + (accuracy - 0.5) * 0.4

        std = metrics.duration_std or 0.0
        risk = prediction.estimated_risk
        if std > _RISK_STD_THRESHOLD:
            risk = risk + (std - _RISK_STD_THRESHOLD)

        return Prediction(
            success_probability=_clamp(success),
            estimated_duration_days=max(0.0, duration),
            estimated_risk=_clamp(risk),
            estimated_effort=prediction.estimated_effort,
            confidence=_clamp(confidence),
            evidence_count=prediction.evidence_count,
        )

    def record_outcome(
        self,
        decision: StrategyDecision,
        goal_type: str = "build",
        actual_success: Optional[bool] = None,
        actual_duration_days: Optional[float] = None,
    ) -> Optional[CalibrationRecord]:
        strategy = decision.chosen_strategy
        if strategy is None or strategy.prediction is None:
            return None
        if actual_success is None:
            actual_success = decision.actual_success
        if actual_success is None:
            actual_success = True
        if actual_duration_days is None:
            actual_duration_days = decision.actual_duration_days
        if actual_duration_days is None:
            actual_duration_days = strategy.prediction.estimated_duration_days
        return self.store.record(
            decision, goal_type, actual_success, actual_duration_days
        )

    def recalibrate(
        self,
        decision: StrategyDecision,
        goal_type: str = "build",
        actual_success: Optional[bool] = None,
        actual_duration_days: Optional[float] = None,
    ) -> Optional[Prediction]:
        self.record_outcome(
            decision, goal_type, actual_success, actual_duration_days
        )
        strategy = decision.chosen_strategy
        if strategy is None or strategy.prediction is None:
            return None
        tags = [_tag_value(t) for t in strategy.tags]
        return self.calibrate(strategy.prediction, goal_type, tags)
