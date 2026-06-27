from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from core.providers.feedback.models import (
    CalibrationConfig, CalibrationEntry, RoutingOutcome,
    _compute_time_weights, _extract_context,
)
from core.providers.feedback.store import FeedbackStore

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = CalibrationConfig()


class CalibrationEngine:
    """Computes and stores time-aware, context-aware calibration adjustments.

    Uses exponential time-decay weighting so recent outcomes influence
    calibration more than older ones. Groups by (language, framework,
    project_size) context with configurable fallback chain.
    """

    def __init__(
        self,
        store: FeedbackStore | None = None,
        config: CalibrationConfig | None = None,
    ):
        from core.providers.feedback.store import FeedbackStore as _FS
        self._store = store or _FS()
        self._config = config or _DEFAULT_CONFIG

    def update_from_outcomes(
        self,
        provider_id: str,
        capability: str,
        force: bool = False,
    ) -> int:
        """Recalculate calibration for all contexts of (provider, capability)
        using time-weighted outcome scoring.

        Returns number of context groups updated.
        """
        outcomes = self._store.get_all_outcomes(
            provider_id=provider_id, capability=capability,
        )
        if not outcomes and not force:
            return 0

        context_groups: dict[tuple[str, str, str], list[RoutingOutcome]] = (
            defaultdict(list)
        )

        for outcome in outcomes:
            decision = self._store.get_decision(outcome.decision_id)
            if decision:
                ctx = _extract_context(decision.task)
                key = (ctx["language"], ctx["framework"], ctx["project_size"])
                context_groups[key].append(outcome)
            else:
                context_groups[("", "", "")].append(outcome)

        all_outcomes = outcomes
        updated = 0

        for (lang, fw, sz), group in context_groups.items():
            result = self._update_single_context(
                provider_id, capability, group, force,
                language=lang, framework=fw, project_size=sz,
            )
            if result:
                updated += 1

        if ("", "", "") not in context_groups and len(all_outcomes) >= self._config.min_evidence:
            result = self._update_single_context(
                provider_id, capability, all_outcomes, force,
            )
            if result:
                updated += 1

        return updated

    def update_from_outcomes_for_context(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
        force: bool = False,
    ) -> CalibrationEntry | None:
        """Update calibration for a specific context only."""
        outcomes = self._store.get_all_outcomes(
            provider_id=provider_id, capability=capability,
        )
        if not outcomes and not force:
            return None

        matching: list[RoutingOutcome] = []
        for outcome in outcomes:
            decision = self._store.get_decision(outcome.decision_id)
            if decision:
                ctx = _extract_context(decision.task)
                if (ctx["language"] == language
                        and ctx["framework"] == framework
                        and ctx["project_size"] == project_size):
                    matching.append(outcome)
            elif language == "" and framework == "" and project_size == "":
                matching.append(outcome)

        return self._update_single_context(
            provider_id, capability, matching, force,
            language=language, framework=framework, project_size=project_size,
        )

    # ── Core computation ───────────────────────────────────────────

    def _compute_weighted_stats(
        self,
        outcomes: list[RoutingOutcome],
        now: float | None = None,
    ) -> tuple[float, float, int]:
        """Compute time-weighted average outcome score and effective N.

        Returns (weighted_avg_score, effective_n, raw_count).
        """
        if not outcomes:
            return 0.0, 0.0, 0

        timestamps = [o.timestamp for o in outcomes]
        weights, effective_n = _compute_time_weights(
            timestamps,
            half_life_days=self._config.half_life_days,
            max_history_days=self._config.maximum_history_days,
            min_weight=self._config.minimum_weight,
            now=now,
        )

        if not weights:
            return 0.0, 0.0, len(outcomes)

        # Filter outcomes matching the surviving weights
        # Build weighted score sum
        weighted_score_sum = 0.0
        weight_idx = 0
        for outcome in outcomes:
            age_days = ((now or time.time()) - outcome.timestamp) / 86400.0
            if age_days > self._config.maximum_history_days:
                continue
            w = __import__("math").exp(-age_days / self._config.half_life_days)
            if w < self._config.minimum_weight:
                continue
            if weight_idx < len(weights):
                weighted_score_sum += weights[weight_idx] * outcome.outcome_score
                weight_idx += 1

        total_weight = sum(weights)
        avg_score = weighted_score_sum / total_weight if total_weight > 0 else 0.0

        return avg_score, effective_n, len(outcomes)

    def _update_single_context(
        self,
        provider_id: str,
        capability: str,
        outcomes: list[RoutingOutcome],
        force: bool = False,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> CalibrationEntry | None:
        total = len(outcomes)
        if total < self._config.min_evidence and not force:
            logger.debug(
                "[CalibrationEngine] %s/%s [%s/%s/%s]: %d outcomes < %d — skipping",
                provider_id, capability, language or "*", framework or "*",
                project_size or "*", total, self._config.min_evidence,
            )
            return None

        now = time.time()
        avg_outcome, effective_n, raw_count = self._compute_weighted_stats(
            outcomes, now=now,
        )

        # If all outcomes were too old, effective_n could be 0
        if effective_n < 1.0 and not force:
            logger.debug(
                "[CalibrationEngine] %s/%s [%s/%s/%s]: effective_n=%.1f too low — skipping",
                provider_id, capability, language or "*", framework or "*",
                project_size or "*", effective_n,
            )
            return None

        # Expected baseline
        expected_baseline = 0.75
        raw_adjustment = avg_outcome - expected_baseline

        # Effective N determines confidence
        evidence_weight = min(1.0, effective_n / self._config.max_evidence)
        confidence = evidence_weight

        # Smooth with existing entry
        existing = self._store.get_calibration(
            provider_id, capability, language, framework, project_size,
        )
        if existing and existing.evidence_count > 0:
            smoothed = (1 - self._config.alpha) * existing.adjustment + self._config.alpha * raw_adjustment
            total_evidence = min(
                existing.evidence_count + raw_count,
                self._config.max_evidence * 2,
            )
            confidence = min(1.0, total_evidence / self._config.max_evidence)
        else:
            smoothed = raw_adjustment
            total_evidence = raw_count

        entry = CalibrationEntry(
            provider_id=provider_id,
            capability=capability,
            adjustment=round(smoothed, 4),
            confidence=round(confidence, 4),
            evidence_count=total_evidence,
            last_updated=now,
            language=language,
            framework=framework,
            project_size=project_size,
        )
        self._store.save_calibration(entry)
        logger.info(
            "[CalibrationEngine] Updated %s/%s [%s/%s/%s]: adj=%+.4f (conf=%.2f, n=%d, eff_n=%.1f)",
            provider_id, capability, language or "*", framework or "*",
            project_size or "*", entry.adjustment, entry.confidence,
            total_evidence, effective_n,
        )
        return entry

    # ── Query-time confidence decay ────────────────────────────────

    def _decay_confidence(
        self, confidence: float, last_updated: float, now: float | None = None,
    ) -> float:
        """Apply exponential time-decay to confidence based on calibration age.

        Returns 0.0 when decayed confidence drops below minimum_weight,
        effectively discarding stale calibrations.
        """
        if confidence <= 0.0:
            return 0.0
        if now is None:
            now = time.time()
        age_days = (now - last_updated) / 86400.0
        if age_days < 0:
            age_days = 0.0
        time_factor = __import__("math").exp(-age_days / self._config.half_life_days)
        decayed = confidence * time_factor
        if decayed < self._config.minimum_weight:
            return 0.0
        return decayed

    def get_adjustment(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> float:
        entry = self._store.get_calibration_fallback(
            provider_id, capability, language, framework, project_size,
        )
        if not entry:
            return 0.0
        decayed = self._decay_confidence(entry.confidence, entry.last_updated)
        if decayed <= 0.0:
            return 0.0
        return entry.adjustment

    def get_adjustment_with_confidence(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> tuple[float, float]:
        entry = self._store.get_calibration_fallback(
            provider_id, capability, language, framework, project_size,
        )
        if not entry:
            return 0.0, 0.0
        decayed = self._decay_confidence(entry.confidence, entry.last_updated)
        return entry.adjustment, decayed

    # ── Batch ──────────────────────────────────────────────────────

    def update_all(self) -> int:
        all_outcomes = self._store.get_all_outcomes(limit=10000)
        pairs: set[tuple[str, str]] = set()

        for outcome in all_outcomes:
            decision = self._store.get_decision(outcome.decision_id)
            if decision:
                pairs.add((decision.selected_provider, decision.capability))

        updated = 0
        for provider_id, capability in pairs:
            updated += self.update_from_outcomes(provider_id, capability)

        logger.info(
            "[CalibrationEngine] update_all complete: %d pairs updated",
            updated,
        )
        return updated

    def get_summary(self) -> list[dict[str, Any]]:
        return self._store.get_calibration_summary()
