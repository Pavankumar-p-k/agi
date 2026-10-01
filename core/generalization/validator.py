"""Principle validation (Phase 14.0/14.3)."""
from __future__ import annotations

from typing import List, Optional

from core.generalization.models import PrincipleCandidate, PrincipleStatus


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class PrincipleValidator:
    """Apply statistical gates and compute principle confidence."""

    def __init__(
        self,
        min_sample_size: int = 10,
        min_domains: int = 2,
        min_support_rate: float = 0.70,
        min_discrimination: float = 0.20,
        min_confidence: float = 0.60,
        causal_filter=None,
        override_causal_check: bool = False,
        belief_integrator=None,
    ) -> None:
        self.min_sample_size = min_sample_size
        self.min_domains = min_domains
        self.min_support_rate = min_support_rate
        self.min_discrimination = min_discrimination
        self.min_confidence = min_confidence
        self._causal_filter = causal_filter
        self.override_causal_check = override_causal_check
        self.belief_integrator = belief_integrator

    def set_causal_filter(self, causal_filter) -> None:
        self._causal_filter = causal_filter

    # ── confidence ───────────────────────────────────────────────────

    @staticmethod
    def _compute_confidence(candidate: PrincipleCandidate) -> float:
        sample = max(0, int(candidate.sample_size))
        sample_factor = sample / (sample + 20.0) if sample else 0.0
        value = (
            0.5
            + 0.4 * max(0.0, candidate.discrimination)
            + 0.3 * sample_factor
        )
        return _clamp(value)

    # ── gates ────────────────────────────────────────────────────────

    def _passes_gates(self, candidate: PrincipleCandidate, confidence: float) -> bool:
        if candidate.sample_size < self.min_sample_size:
            return False
        if len(candidate.domains) < self.min_domains:
            return False
        if candidate.support_rate < self.min_support_rate:
            return False
        if candidate.discrimination < self.min_discrimination:
            return False
        if confidence < self.min_confidence:
            return False
        return True

    # ── public API ───────────────────────────────────────────────────

    def validate(
        self, candidate: PrincipleCandidate, data_points: Optional[List] = None
    ) -> PrincipleCandidate:
        confidence = self._compute_confidence(candidate)

        if self.belief_integrator is not None:
            try:
                adjusted = self.belief_integrator.adjust_principle_confidence(
                    discrimination=candidate.discrimination,
                    sample_size=candidate.sample_size,
                    domains=list(candidate.domains),
                )
                confidence = adjusted.overall
            except Exception:
                pass

        candidate.confidence = confidence

        if not self._passes_gates(candidate, confidence):
            candidate.status = PrincipleStatus.CANDIDATE
            return candidate

        if (
            self._causal_filter is not None
            and data_points
            and not self.override_causal_check
        ):
            analysis = self._causal_filter.analyze(candidate, data_points)
            if analysis.status.value == "likely_confounded":
                candidate.status = PrincipleStatus.CANDIDATE
                return candidate

        candidate.status = PrincipleStatus.ACCEPTED
        return candidate

    def is_accepted(
        self, candidate: PrincipleCandidate, data_points: Optional[List] = None
    ) -> bool:
        return self.validate(candidate, data_points).status == PrincipleStatus.ACCEPTED
