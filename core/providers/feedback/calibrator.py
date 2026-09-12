"""CalibrationEngine: learns per-(provider, capability, context) adjustments.

Completed from the committed contract in tests/unit/test_provider_feedback.py
(CalibrationEngine section).

Model:
- Outcomes are grouped by the task context extracted from their routing
  decision (language / framework / project_size).
- Each group's adjustment = ``alpha * (2p - 1)`` where ``p`` is the
  time-decayed mean of composite outcome scores — so consistently good
  performance yields a positive adjustment, poor performance negative.
- ``min_evidence`` gates non-forced updates (insufficient evidence → 0
  groups updated); ``force=True`` bypasses the gate.
- ``evidence_count`` is capped at ``max_evidence``; confidence at query time
  = (evidence_count / max_evidence) × time-decay of the entry's own
  ``last_updated`` — an aged calibration loses influence, and a fully decayed
  one returns 0.0 adjustment.
- Lookups use the store's context fallback chain (specific → generic).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Optional

from core.providers.feedback.models import (
    CalibrationConfig,
    _extract_context,
    _compute_time_weights,
)

logger = logging.getLogger(__name__)


class CalibrationEngine:
    """Computes and serves context-aware provider calibration adjustments."""

    def __init__(self, store: Any, config: Optional[CalibrationConfig] = None) -> None:
        self._store = store
        self.config = config or CalibrationConfig()

    # ------------------------------------------------------------------ #
    # Update (learn)                                                     #
    # ------------------------------------------------------------------ #

    def update_from_outcomes(
        self,
        provider_id: str,
        capability: str,
        force: bool = False,
    ) -> int:
        """Recompute calibrations for every context group of this pair.

        Returns the number of context groups updated (0 when evidence is
        insufficient and not forced).
        """
        pairs = self._store.get_outcomes_with_decisions(
            provider_id=provider_id, capability=capability,
        )
        if not pairs:
            return 0
        groups: dict[tuple[str, str, str], list[tuple[Any, Any]]] = defaultdict(list)
        for outcome, decision in pairs:
            ctx = _extract_context(decision.task)
            groups[(ctx["language"], ctx["framework"], ctx["project_size"])].append(
                (outcome, decision)
            )
        updated = 0
        for ctx_tuple, group in groups.items():
            entry = self._compute_entry(provider_id, capability, ctx_tuple, group)
            if entry is None:
                continue
            if not force and len(group) < self.config.min_evidence:
                continue
            self._store.save_calibration(entry)
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
    ) -> Optional[Any]:
        """Recompute only the exact context group; None when no outcomes match
        it or their effective weight is zero (all filtered by age)."""
        pairs = self._store.get_outcomes_with_decisions(
            provider_id=provider_id, capability=capability,
        )
        group = []
        for outcome, decision in pairs:
            ctx = _extract_context(decision.task)
            if (ctx["language"], ctx["framework"], ctx["project_size"]) == (
                language, framework, project_size,
            ):
                group.append((outcome, decision))
        if not group:
            return None
        entry = self._compute_entry(
            provider_id, capability, (language, framework, project_size), group,
        )
        if entry is None:
            return None
        if not force and len(group) < self.config.min_evidence:
            return entry if entry.evidence_count >= self.config.min_evidence else None
        self._store.save_calibration(entry)
        return entry

    def update_all(self, force: bool = False) -> int:
        """Recompute calibrations for every (provider, capability) pair on file."""
        pairs = self._store.get_outcomes_with_decisions()
        seen: set[tuple[str, str]] = set()
        for _outcome, decision in pairs:
            if decision.selected_provider and decision.capability:
                seen.add((decision.selected_provider, decision.capability))
        total = 0
        for provider_id, capability in sorted(seen):
            total += self.update_from_outcomes(provider_id, capability, force=force)
        return total

    # ------------------------------------------------------------------ #
    # Query (serve)                                                      #
    # ------------------------------------------------------------------ #

    def get_adjustment(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> float:
        adj, _conf = self.get_adjustment_with_confidence(
            provider_id, capability,
            language=language, framework=framework, project_size=project_size,
        )
        return adj

    def get_adjustment_with_confidence(
        self,
        provider_id: str,
        capability: str,
        language: str = "",
        framework: str = "",
        project_size: str = "",
    ) -> tuple[float, float]:
        entry = self._store.get_calibration_fallback(
            provider_id, capability,
            language=language, framework=framework, project_size=project_size,
        )
        if entry is None:
            return 0.0, 0.0
        age_weight = self._entry_age_weight(entry)
        if age_weight <= self.config.minimum_weight:
            return 0.0, 0.0
        conf = min(1.0, entry.evidence_count / max(1, self.config.max_evidence))
        conf *= age_weight
        return entry.adjustment, round(conf, 4)

    def get_summary(self) -> list[dict[str, Any]]:
        return self._store.get_calibration_summary()

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _entry_age_weight(self, entry: Any) -> float:
        import time

        cfg = self.config
        age_days = max(0.0, (time.time() - entry.last_updated) / 86400.0)
        if age_days > cfg.maximum_history_days:
            return 0.0
        if cfg.half_life_days > 0:
            return 0.5 ** (age_days / cfg.half_life_days)
        return 1.0

    def _compute_entry(
        self,
        provider_id: str,
        capability: str,
        ctx_tuple: tuple[str, str, str],
        group: list[tuple[Any, Any]],
    ) -> Optional[Any]:
        """Build the CalibrationEntry for one context group (no side effects).

        Returns None when every outcome in the group is filtered out by the
        time window (effective weight zero).
        """
        import time as _time

        from core.providers.feedback.models import CalibrationEntry

        cfg = self.config
        timestamps = [float(outcome.timestamp) for outcome, _d in group]
        weights, effective_n = _compute_time_weights(
            timestamps,
            half_life_days=cfg.half_life_days,
            max_history_days=cfg.maximum_history_days,
            min_weight=cfg.minimum_weight,
        )
        if effective_n <= 0 or not weights:
            return None

        # Time-decayed mean of composite outcome scores.
        # The i-th weight aligns with the i-th KEPT timestamp, so build the
        # kept list in the same pass order as _compute_time_weights.
        kept: list[tuple[float, float]] = []
        now = _time.time()
        for (outcome, _d), ts in zip(group, timestamps):
            age_days = max(0.0, (now - ts) / 86400.0)
            if age_days > cfg.maximum_history_days:
                continue
            w = 0.5 ** (age_days / cfg.half_life_days) if cfg.half_life_days > 0 else 1.0
            if w < cfg.minimum_weight:
                continue
            kept.append((w, float(outcome.outcome_score)))

        total_w = sum(w for w, _s in kept)
        if total_w <= 0:
            return None
        p = sum(w * s for w, s in kept) / total_w
        adjustment = round(cfg.alpha * (2.0 * p - 1.0), 4)

        evidence_count = min(len(group), cfg.max_evidence)
        confidence = min(1.0, evidence_count / max(1, cfg.max_evidence))
        language, framework, project_size = ctx_tuple
        return CalibrationEntry(
            provider_id=provider_id,
            capability=capability,
            adjustment=adjustment,
            confidence=round(confidence, 4),
            evidence_count=evidence_count,
            last_updated=_time.time(),
            language=language,
            framework=framework,
            project_size=project_size,
        )
