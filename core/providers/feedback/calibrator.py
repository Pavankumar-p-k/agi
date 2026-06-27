from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.feedback.models import CalibrationEntry
from core.providers.feedback.store import FeedbackStore

logger = logging.getLogger(__name__)

_MIN_EVIDENCE_FOR_CALIBRATION = 3
"""Minimum number of outcomes before calibration starts affecting scores."""

_MAX_EVIDENCE_CAP = 50
"""Beyond this many outcomes, new data has diminishing weight."""

_DEFAULT_ADJUSTMENT_ALPHA = 0.3
"""Smoothing factor for moving-average adjustment updates."""


class CalibrationEngine:
    """Computes and stores calibration adjustments from historical outcomes.

    For each (provider_id, capability) pair, the engine tracks the
    average outcome score and computes an adjustment that the router
    adds to the provider's base score during selection.
    """

    def __init__(self, store: FeedbackStore | None = None):
        from core.providers.feedback.store import FeedbackStore as _FS
        self._store = store or _FS()
        self._min_evidence = _MIN_EVIDENCE_FOR_CALIBRATION
        self._max_evidence = _MAX_EVIDENCE_CAP
        self._alpha = _DEFAULT_ADJUSTMENT_ALPHA

    def update_from_outcomes(
        self,
        provider_id: str,
        capability: str,
        force: bool = False,
    ) -> CalibrationEntry | None:
        """Recalculate the calibration entry for (provider, capability)
        based on all recorded outcomes.

        Returns the updated CalibrationEntry, or None if insufficient
        evidence and not forced.
        """
        outcomes = self._store.get_all_outcomes(
            provider_id=provider_id, capability=capability,
        )
        if not outcomes and not force:
            return None

        total = len(outcomes)
        if total < self._min_evidence and not force:
            logger.debug(
                "[CalibrationEngine] %s/%s: %d outcomes < %d min evidence — skipping",
                provider_id, capability, total, self._min_evidence,
            )
            return None

        # Compute average outcome score
        avg_outcome = sum(o.outcome_score for o in outcomes) / total if total else 0.0

        # Expected baseline is 0.75 (reasonable default for a capable provider)
        expected_baseline = 0.75

        # Raw adjustment = avg_outcome - expected_baseline
        raw_adjustment = avg_outcome - expected_baseline

        # Confidence grows with evidence, saturating at max_evidence
        evidence_weight = min(1.0, total / self._max_evidence)
        confidence = evidence_weight

        # Smooth adjustment with moving average against existing entry
        existing = self._store.get_calibration(provider_id, capability)
        if existing and existing.evidence_count > 0:
            smoothed = (1 - self._alpha) * existing.adjustment + self._alpha * raw_adjustment
            total_evidence = min(existing.evidence_count + total, self._max_evidence * 2)
            confidence = min(1.0, total_evidence / self._max_evidence)
        else:
            smoothed = raw_adjustment
            total_evidence = total

        entry = CalibrationEntry(
            provider_id=provider_id,
            capability=capability,
            adjustment=round(smoothed, 4),
            confidence=round(confidence, 4),
            evidence_count=total_evidence,
            last_updated=time.time(),
        )
        self._store.save_calibration(entry)

        logger.info(
            "[CalibrationEngine] Updated %s/%s: adj=%+.4f (conf=%.2f, n=%d)",
            provider_id, capability, entry.adjustment, entry.confidence, total_evidence,
        )
        return entry

    def get_adjustment(
        self, provider_id: str, capability: str,
    ) -> float:
        """Get the effective calibration adjustment for a (provider, capability).

        Returns 0.0 if no calibration data exists or confidence is too low.
        """
        entry = self._store.get_calibration(provider_id, capability)
        if not entry:
            return 0.0
        if entry.confidence <= 0.0:
            return 0.0
        return entry.adjustment

    def get_adjustment_with_confidence(
        self, provider_id: str, capability: str,
    ) -> tuple[float, float]:
        """Returns (adjustment, confidence) for a (provider, capability)."""
        entry = self._store.get_calibration(provider_id, capability)
        if not entry:
            return 0.0, 0.0
        return entry.adjustment, entry.confidence

    def update_all(self) -> int:
        """Recalculate calibrations for all (provider, capability) pairs
        that have outcomes.

        Returns the number of updated entries.
        """
        all_outcomes = self._store.get_all_outcomes(limit=10000)
        pairs: set[tuple[str, str]] = set()

        for outcome in all_outcomes:
            decision = self._store.get_decision(outcome.decision_id)
            if decision:
                pairs.add((decision.selected_provider, decision.capability))

        updated = 0
        for provider_id, capability in pairs:
            result = self.update_from_outcomes(provider_id, capability)
            if result:
                updated += 1

        logger.info(
            "[CalibrationEngine] update_all complete: %d/%d pairs updated",
            updated, len(pairs),
        )
        return updated

    def get_summary(self) -> list[dict[str, Any]]:
        return self._store.get_calibration_summary()
