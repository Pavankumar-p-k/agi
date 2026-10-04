"""Workflow calibration engine.

Computes weighted reliability statistics from workflow history, decays
confidence over time, and serves predictions with fingerprint fallback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core.providers.feedback.models import CalibrationConfig
from core.workflow.learning_models import (
    RecoveryMode,
    WorkflowOutcome,
    _fingerprint_fallback_key,
    _parse_fingerprint_key,
)
from core.workflow.learning_store import (
    WorkflowCalibrationStore,
    WorkflowHistoryStore,
)

_RECOVERED_MODES = {
    RecoveryMode.AFTER_RETRY,
    RecoveryMode.AFTER_REPLAN,
    RecoveryMode.AFTER_PROVIDER_SWAP,
    RecoveryMode.AFTER_COMPENSATION,
    RecoveryMode.AFTER_HUMAN_APPROVAL,
}


@dataclass
class WorkflowCalibrationMetrics:
    """Weighted statistics over a group of workflow outcomes."""

    evidence_count: int = 0
    success_rate: float = 0.0
    first_try_rate: float = 0.0
    recovered_rate: float = 0.0
    failed_rate: float = 0.0
    avg_duration_ms: float = 0.0
    avg_cost: float = 0.0
    avg_quality: float = 0.0
    confidence: float = 0.0


@dataclass
class WorkflowPrediction:
    """A calibration-backed prediction for one workflow template."""

    template_id: str = ""
    expected_success: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0
    first_try_probability: float = 0.0
    failed_probability: float = 0.0
    recovered_probability: float = 0.0


def _compute_weighted_stats(
    outcomes: list[WorkflowOutcome],
    config: CalibrationConfig,
) -> WorkflowCalibrationMetrics:
    n = len(outcomes)
    if n == 0:
        return WorkflowCalibrationMetrics()

    successes = sum(1 for o in outcomes if o.success)
    first_try = sum(
        1 for o in outcomes if o.recovery_mode == RecoveryMode.FIRST_TRY
    )
    recovered = sum(1 for o in outcomes if o.recovery_mode in _RECOVERED_MODES)
    failed = sum(
        1 for o in outcomes if o.recovery_mode == RecoveryMode.FAILED
    )

    success_rate = successes / n
    first_try_rate = first_try / n
    recovered_rate = recovered / n
    failed_rate = failed / n
    avg_duration_ms = sum(o.duration_ms for o in outcomes) / n
    avg_cost = sum(o.cost for o in outcomes) / n
    avg_quality = sum(o.quality for o in outcomes) / n

    max_evidence = int(getattr(config, "max_evidence", 50) or 50)
    evidence_factor = min(n / max(max_evidence, 1), 1.0)
    quality_variance = sum(
        (o.quality - avg_quality) ** 2 for o in outcomes
    ) / n
    variance_factor = 1.0 / (1.0 + quality_variance)
    stability = abs(2.0 * success_rate - 1.0)
    confidence = (
        0.4 * evidence_factor
        + 0.3 * variance_factor
        + 0.3 * stability
    )
    confidence = max(0.0, min(1.0, confidence))

    return WorkflowCalibrationMetrics(
        evidence_count=n,
        success_rate=success_rate,
        first_try_rate=first_try_rate,
        recovered_rate=recovered_rate,
        failed_rate=failed_rate,
        avg_duration_ms=avg_duration_ms,
        avg_cost=avg_cost,
        avg_quality=avg_quality,
        confidence=confidence,
    )


def _decay_confidence(
    confidence: float,
    timestamp: float,
    config: CalibrationConfig,
    now: float | None = None,
) -> float:
    """Exponentially decay a confidence value by age (half-life)."""
    if confidence is None or confidence <= 0.0:
        return 0.0
    if now is None:
        now = time.time()
    half_life = float(getattr(config, "half_life_days", 100.0) or 0.0)
    if half_life <= 0.0:
        return 0.0
    # Whole-second ages keep decay deterministic across rapid calls.
    age_seconds = int(max(0.0, now - float(timestamp)))
    age_days = age_seconds / 86400.0
    decayed = float(confidence) * (0.5 ** (age_days / half_life))
    minimum = float(getattr(config, "minimum_weight", 0.05) or 0.0)
    if decayed < minimum:
        return 0.0
    return decayed


class WorkflowCalibrationEngine:
    """Predicts workflow success from stored calibration entries."""

    def __init__(
        self,
        history_store: WorkflowHistoryStore | None = None,
        calibration_store: WorkflowCalibrationStore | None = None,
        config: CalibrationConfig | None = None,
    ) -> None:
        self._history = (
            history_store
            if history_store is not None
            else WorkflowHistoryStore()
        )
        self._calibration = (
            calibration_store
            if calibration_store is not None
            else WorkflowCalibrationStore()
        )
        self._config = (
            config if config is not None else CalibrationConfig()
        )

    def predict(
        self,
        template_id: str,
        template_version: int = 1,
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
    ) -> WorkflowPrediction:
        entry = self._calibration.get_calibration_fallback(
            template_id=template_id,
            template_version=template_version,
            task_type=task_type,
            languages=languages,
            frameworks=frameworks,
            project_size=project_size,
        )
        if entry is None:
            return WorkflowPrediction(template_id=template_id)

        confidence = _decay_confidence(
            float(entry.get("confidence", 0.0) or 0.0),
            float(entry.get("updated_at", 0.0) or 0.0),
            self._config,
        )
        success_rate = float(entry.get("success_rate", 0.0) or 0.0)
        return WorkflowPrediction(
            template_id=template_id,
            expected_success=success_rate if confidence > 0.0 else 0.0,
            confidence=confidence,
            evidence_count=int(entry.get("evidence_count", 0) or 0),
            first_try_probability=float(
                entry.get("first_try_rate", 0.0) or 0.0
            ),
            failed_probability=max(0.0, 1.0 - success_rate),
            recovered_probability=float(
                entry.get("recovered_rate", 0.0) or 0.0
            ),
        )

    def get_prediction(self, *args, **kwargs) -> WorkflowPrediction:
        """Alias for predict()."""
        return self.predict(*args, **kwargs)

    def recalibrate(
        self, template_id: str, template_version: int = 1
    ) -> int:
        outcomes = self._history.get_outcomes(
            template_id=template_id,
            template_version=template_version,
        )
        if not outcomes:
            return 0

        groups: dict[str, list[WorkflowOutcome]] = {}
        for outcome in outcomes:
            parsed = _parse_fingerprint_key(outcome.fingerprint_key or "")
            canonical = _fingerprint_fallback_key(
                task_type=parsed["task_type"],
                languages=parsed["languages"],
                frameworks=parsed["frameworks"],
                project_size=parsed["project_size"],
            )
            groups.setdefault(canonical, []).append(outcome)

        min_evidence = int(getattr(self._config, "min_evidence", 3) or 0)
        saved = 0
        for key, group in groups.items():
            if len(group) < min_evidence:
                continue
            metrics = _compute_weighted_stats(group, self._config)
            parsed = _parse_fingerprint_key(key)
            self._calibration.save_calibration(
                template_id=template_id,
                template_version=template_version,
                fingerprint_key=key,
                task_type=parsed["task_type"],
                project_size=parsed["project_size"],
                languages=parsed["languages"],
                frameworks=parsed["frameworks"],
                success_rate=metrics.success_rate,
                avg_duration_ms=metrics.avg_duration_ms,
                avg_cost=metrics.avg_cost,
                avg_quality=metrics.avg_quality,
                first_try_rate=metrics.first_try_rate,
                recovered_rate=metrics.recovered_rate,
                confidence=metrics.confidence,
                evidence_count=metrics.evidence_count,
            )
            saved += 1
        return saved

    def recalibrate_all(self) -> int:
        outcomes = self._history.get_outcomes()
        pairs = {
            (o.template_id, o.template_version) for o in outcomes
        }
        return sum(
            self.recalibrate(template_id, template_version=version)
            for template_id, version in pairs
        )
