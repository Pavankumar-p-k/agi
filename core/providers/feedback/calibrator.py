from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from core.providers.feedback.models import (
    CalibrationEntry, RoutingOutcome, _extract_context,
)
from core.providers.feedback.store import FeedbackStore

logger = logging.getLogger(__name__)

_MIN_EVIDENCE_FOR_CALIBRATION = 3
_MAX_EVIDENCE_CAP = 50
_DEFAULT_ADJUSTMENT_ALPHA = 0.3


class CalibrationEngine:
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
    ) -> int:
        """Recalculate calibration for all contexts of (provider, capability).

        Groups outcomes by (language, framework, project_size) context
        and computes separate calibrations per context + generic fallback.

        Returns number of context groups updated.
        """
        outcomes = self._store.get_all_outcomes(
            provider_id=provider_id, capability=capability,
        )
        if not outcomes and not force:
            return 0

        context_groups: dict[tuple[str, str, str], list[RoutingOutcome]] = defaultdict(list)

        for outcome in outcomes:
            decision = self._store.get_decision(outcome.decision_id)
            if decision:
                ctx = _extract_context(decision.task)
                key = (ctx["language"], ctx["framework"], ctx["project_size"])
                context_groups[key].append(outcome)
            else:
                context_groups[("", "", "")].append(outcome)

        # Always compute generic (no context) from ALL outcomes as fallback
        all_outcomes = outcomes

        updated = 0
        for (lang, fw, sz), group in context_groups.items():
            result = self._update_single_context(
                provider_id, capability, group, force,
                language=lang, framework=fw, project_size=sz,
            )
            if result:
                updated += 1

        # Ensure generic (all-empty) calibration exists even if no explicit
        # bare-context outcomes exist
        if ("", "", "") not in context_groups and len(all_outcomes) >= self._min_evidence:
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
        """Update calibration for a specific context only.

        Finds outcomes whose decision's task matches the given context
        and recomputes just that context's calibration.
        """
        outcomes = self._store.get_all_outcomes(
            provider_id=provider_id, capability=capability,
        )
        if not outcomes and not force:
            return None

        # Filter outcomes matching the given context
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
        if total < self._min_evidence and not force:
            logger.debug(
                "[CalibrationEngine] %s/%s [%s/%s/%s]: %d outcomes < %d — skipping",
                provider_id, capability, language or "*", framework or "*",
                project_size or "*", total, self._min_evidence,
            )
            return None

        avg_outcome = sum(o.outcome_score for o in outcomes) / total if total else 0.0
        expected_baseline = 0.75
        raw_adjustment = avg_outcome - expected_baseline

        evidence_weight = min(1.0, total / self._max_evidence)
        confidence = evidence_weight

        existing = self._store.get_calibration(
            provider_id, capability, language, framework, project_size,
        )
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
            language=language,
            framework=framework,
            project_size=project_size,
        )
        self._store.save_calibration(entry)
        logger.info(
            "[CalibrationEngine] Updated %s/%s [%s/%s/%s]: adj=%+.4f (conf=%.2f, n=%d)",
            provider_id, capability, language or "*", framework or "*",
            project_size or "*", entry.adjustment, entry.confidence, total_evidence,
        )
        return entry

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
        if not entry or entry.confidence <= 0.0:
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
        return entry.adjustment, entry.confidence

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
