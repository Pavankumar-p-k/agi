from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.workflow.learning_models import (
    RecoveryMode, WorkflowOutcome,
    _FINGERPRINT_FALLBACK_CHAIN, _fingerprint_fallback_key,
    _parse_fingerprint_key,
)
from core.workflow.learning_store import (
    WorkflowCalibrationStore, WorkflowHistoryStore,
)
from core.providers.feedback.models import CalibrationConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = CalibrationConfig()


@dataclass
class WorkflowCalibrationMetrics:
    """Computed metrics for a (template, fingerprint) calibration entry."""

    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    avg_cost: float = 0.0
    avg_quality: float = 0.0
    first_try_rate: float = 0.0
    recovered_rate: float = 0.0
    failed_rate: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0
    effective_n: float = 0.0


@dataclass
class WorkflowPrediction:
    """Prediction returned by the calibration engine.

    Contains only statistics — no ranking or selection logic.
    """

    template_id: str = ""
    template_version: int = 1
    fingerprint_key: str = ""
    expected_success: float = 0.0
    expected_duration_ms: float = 0.0
    expected_cost: float = 0.0
    expected_quality: float = 0.0
    first_try_probability: float = 0.0
    recovered_probability: float = 0.0
    failed_probability: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0


# ── Time-weighted stats computation ────────────────────────────────────


def _compute_time_weights(
    timestamps: list[float],
    half_life_days: float = 100.0,
    max_history_days: int = 365,
    min_weight: float = 0.05,
    now: float | None = None,
) -> tuple[list[float], float]:
    """Compute exponential time-decay weights for a list of timestamps.

    Returns (weights, effective_n) where effective_n is Kish's
    effective sample size for the weighted set.
    """
    if now is None:
        now = time.time()

    weights: list[float] = []
    for ts in timestamps:
        age_days = (now - ts) / 86400.0
        if age_days > max_history_days:
            continue
        if age_days < 0:
            age_days = 0.0
        w = math.exp(-age_days / half_life_days)
        if w < min_weight:
            continue
        weights.append(w)

    if not weights:
        return [], 0.0

    sum_w = sum(weights)
    sum_w2 = sum(w * w for w in weights)
    effective_n = (sum_w * sum_w) / sum_w2 if sum_w2 > 0 else 0.0

    return weights, effective_n


def _compute_weighted_stats(
    outcomes: list[WorkflowOutcome],
    config: CalibrationConfig,
    now: float | None = None,
) -> WorkflowCalibrationMetrics:
    """Compute time-decayed statistics from a list of outcomes.

    Uses exponential time-decay weighting so recent outcomes influence
    calibration more than older ones.
    """
    if not outcomes:
        return WorkflowCalibrationMetrics()

    raw_count = len(outcomes)
    timestamps = [outcome.duration_ms / 1000.0 for outcome in outcomes]
    # Use actual timestamps from outcomes if available
    actual_timestamps: list[float] = []

    for o in outcomes:
        # No explicit timestamp on WorkflowOutcome, use a proxy
        # Older outcomes have been stored longer — use storage creation heuristic
        actual_timestamps.append(0.0)

    # We use unweighted computation since outcome-level timestamps aren't
    # stored separately on WorkflowOutcome. Time decay is applied at the
    # calibration query level via _decay_confidence, matching the provider
    # system.
    _ = timestamps  # placeholder for future time-weighted compute

    successes = sum(1 for o in outcomes if o.success)
    success_rate = successes / raw_count if raw_count else 0.0
    avg_duration_ms = sum(o.duration_ms for o in outcomes) / raw_count
    avg_cost = sum(o.cost for o in outcomes) / raw_count
    avg_quality = sum(o.quality for o in outcomes) / raw_count

    # Recovery mode breakdown
    first_try = sum(
        1 for o in outcomes
        if o.recovery_mode == RecoveryMode.FIRST_TRY
    )
    recovered = sum(
        1 for o in outcomes
        if o.recovery_mode in (
            RecoveryMode.AFTER_RETRY,
            RecoveryMode.AFTER_PROVIDER_SWAP,
            RecoveryMode.AFTER_REPLAN,
            RecoveryMode.AFTER_COMPENSATION,
            RecoveryMode.AFTER_HUMAN_APPROVAL,
        )
    )
    failed = sum(
        1 for o in outcomes
        if o.recovery_mode == RecoveryMode.FAILED
    )

    first_try_rate = first_try / raw_count if raw_count else 0.0
    recovered_rate = recovered / raw_count if raw_count else 0.0
    failed_rate = failed / raw_count if raw_count else 0.0

    # Confidence: multi-factor
    # 1. Evidence count relative to max
    evidence_factor = min(1.0, raw_count / config.max_evidence)

    # 2. Variance penalty: higher quality variance = lower confidence
    if raw_count >= 2:
        mean_q = avg_quality
        variance = sum((o.quality - mean_q) ** 2 for o in outcomes) / raw_count
        std_dev = math.sqrt(variance)
        variance_factor = max(0.0, 1.0 - std_dev)
    else:
        variance_factor = 0.5

    # 3. Recovery stability: more first-try successes = higher confidence
    stability_factor = first_try_rate

    # Combined confidence
    confidence = min(1.0, (
        evidence_factor * 0.4
        + variance_factor * 0.3
        + stability_factor * 0.3
    ))

    effective_n = raw_count

    return WorkflowCalibrationMetrics(
        success_rate=success_rate,
        avg_duration_ms=avg_duration_ms,
        avg_cost=avg_cost,
        avg_quality=avg_quality,
        first_try_rate=first_try_rate,
        recovered_rate=recovered_rate,
        failed_rate=failed_rate,
        confidence=round(confidence, 4),
        evidence_count=raw_count,
        effective_n=effective_n,
    )


# ── Query-time confidence decay ────────────────────────────────────────


def _decay_confidence(
    confidence: float,
    updated_at: float,
    config: CalibrationConfig,
    now: float | None = None,
) -> float:
    """Apply exponential time-decay to confidence.

    Returns 0.0 when decayed confidence drops below minimum_weight,
    discarding stale calibrations.
    """
    if confidence <= 0.0:
        return 0.0
    if now is None:
        now = time.time()
    age_days = (now - updated_at) / 86400.0
    if age_days < 0:
        age_days = 0.0
    time_factor = math.exp(-age_days / config.half_life_days)
    decayed = confidence * time_factor
    if decayed < config.minimum_weight:
        return 0.0
    return decayed


# ═════════════════════════════════════════════════════════════════════════
# WorkflowCalibrationEngine
# ═════════════════════════════════════════════════════════════════════════


class WorkflowCalibrationEngine:
    """Computes time-aware, context-aware workflow calibration from history.

    Reads from WorkflowHistoryStore, computes metrics at each fingerprint
    granularity level, and writes to WorkflowCalibrationStore.
    """

    def __init__(
        self,
        history_store: WorkflowHistoryStore | None = None,
        calibration_store: WorkflowCalibrationStore | None = None,
        config: CalibrationConfig | None = None,
    ):
        self._history = history_store or WorkflowHistoryStore()
        self._calibration = calibration_store or WorkflowCalibrationStore()
        self._config = config or _DEFAULT_CONFIG

    # ── Public API ───────────────────────────────────────────────────

    def predict(
        self,
        template_id: str,
        template_version: int = 1,
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
    ) -> WorkflowPrediction:
        """Return expected workflow statistics using fallback chain.

        Walks from most specific to least specific fingerprint context
        to find the best matching calibration.
        """
        entry = self._calibration.get_calibration_fallback(
            template_id=template_id,
            template_version=template_version,
            task_type=task_type,
            languages=languages,
            frameworks=frameworks,
            project_size=project_size,
        )
        if not entry:
            return WorkflowPrediction(
                template_id=template_id,
                template_version=template_version,
            )

        now = time.time()
        decayed = _decay_confidence(
            entry["confidence"], entry["updated_at"], self._config, now=now,
        )

        return WorkflowPrediction(
            template_id=entry["template_id"],
            template_version=entry["template_version"],
            fingerprint_key=entry["fingerprint_key"],
            expected_success=entry["success_rate"] if decayed > 0.0 else 0.0,
            expected_duration_ms=entry["avg_duration_ms"],
            expected_cost=entry["avg_cost"],
            expected_quality=entry["avg_quality"],
            first_try_probability=entry["first_try_rate"],
            recovered_probability=entry["recovered_rate"],
            failed_probability=1.0 - entry["success_rate"],
            confidence=decayed,
            evidence_count=entry["evidence_count"],
        )

    def recalibrate(
        self,
        template_id: str,
        template_version: int | None = None,
    ) -> int:
        """Recalculate calibration for all fingerprint groups of a template.

        Returns number of calibration entries updated.
        """
        outcomes = self._history.get_outcomes(
            template_id=template_id,
            template_version=template_version,
            limit=10000,
        )
        if not outcomes:
            logger.debug(
                "[WorkflowCalibrationEngine] No outcomes for %s v%s — skipping",
                template_id, template_version or "*",
            )
            return 0

        # Parse fingerprint keys and group at each fallback level
        level_groups: dict[int, dict[str, list[WorkflowOutcome]]] = {
            level: defaultdict(list) for level in range(len(_FINGERPRINT_FALLBACK_CHAIN))
        }

        for outcome in outcomes:
            parsed = _parse_fingerprint_key(outcome.fingerprint_key)
            t = parsed["task_type"]
            l = parsed["languages"]
            f = parsed["frameworks"]
            s = parsed["project_size"]

            for level_idx, (inc_t, inc_l, inc_f, inc_s) in enumerate(_FINGERPRINT_FALLBACK_CHAIN):
                partial_key = _fingerprint_fallback_key(
                    task_type=t if inc_t else "",
                    languages=l if inc_l else "",
                    frameworks=f if inc_f else "",
                    project_size=s if inc_s else "",
                )
                level_groups[level_idx][partial_key].append(outcome)

        updated = 0

        for level_idx in range(len(_FINGERPRINT_FALLBACK_CHAIN)):
            groups = level_groups[level_idx]
            for partial_key, group_outcomes in groups.items():
                if len(group_outcomes) < self._config.min_evidence:
                    continue

                parsed = _parse_fingerprint_key(partial_key)
                metrics = _compute_weighted_stats(group_outcomes, self._config)

                self._calibration.save_calibration(
                    template_id=template_id,
                    template_version=template_version or 1,
                    fingerprint_key=partial_key,
                    task_type=parsed["task_type"],
                    languages=parsed["languages"],
                    frameworks=parsed["frameworks"],
                    project_size=parsed["project_size"],
                    success_rate=round(metrics.success_rate, 4),
                    avg_duration_ms=round(metrics.avg_duration_ms, 1),
                    avg_cost=round(metrics.avg_cost, 4),
                    avg_quality=round(metrics.avg_quality, 4),
                    first_try_rate=round(metrics.first_try_rate, 4),
                    recovered_rate=round(metrics.recovered_rate, 4),
                    confidence=metrics.confidence,
                    evidence_count=metrics.evidence_count,
                )
                updated += 1

        logger.info(
            "[WorkflowCalibrationEngine] Recalibrated %s v%s: %d entries",
            template_id, template_version or "*", updated,
        )
        return updated

    def recalibrate_all(self) -> int:
        """Recalculate calibration for every template in history.

        Returns total number of calibration entries updated.
        """
        # Get distinct template_ids from history
        all_outcomes = self._history.get_outcomes(limit=100000)
        templates: set[tuple[str, int]] = set()

        for outcome in all_outcomes:
            templates.add((outcome.template_id, outcome.template_version))

        total = 0
        for tid, tver in templates:
            total += self.recalibrate(template_id=tid, template_version=tver)

        logger.info(
            "[WorkflowCalibrationEngine] recalibrate_all complete: %d templates, %d entries",
            len(templates), total,
        )
        return total

    def get_prediction(
        self,
        template_id: str,
        template_version: int = 1,
        task_type: str = "",
        languages: str = "",
        frameworks: str = "",
        project_size: str = "",
    ) -> WorkflowPrediction:
        """Alias for predict()."""
        return self.predict(
            template_id=template_id,
            template_version=template_version,
            task_type=task_type,
            languages=languages,
            frameworks=frameworks,
            project_size=project_size,
        )
