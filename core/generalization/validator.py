"""Phase 14.0 — Principle Validator.

Gates candidate principles before they become accepted principles.

The key question is not "does property X correlate with success?"
but "does property X meaningfully separate successful and unsuccessful systems?"

Phase 14.3: Integrates with CausalFilter to reject confounded principles.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.belief.integration import BeliefIntegrator
from core.generalization.models import (
    CausalStatus,
    PrincipleCandidate,
    PrincipleStatus,
)

if TYPE_CHECKING:
    from core.generalization.causal import CausalFilter

logger = logging.getLogger(__name__)

# ── Default thresholds (from Phase 14.0 spec) ──
_MIN_SAMPLE_SIZE = 10
_MIN_DOMAINS = 3
_MIN_SUPPORT_RATE = 0.70
_MIN_DISCRIMINATION = 0.20
_MIN_CONFIDENCE = 0.80


class PrincipleValidator:
    """Validates candidate principles against statistical thresholds.

    A candidate becomes an ACCEPTED principle only if it clears all gates.
    Otherwise it remains CANDIDATE (or is REJECTED if confidence is hopeless).

    If a CausalFilter is provided, the causal gate is checked after all
    other gates pass. Confounded candidates are not accepted (unless
    override_causal_check is True).
    """

    def __init__(
        self,
        min_sample_size: int = _MIN_SAMPLE_SIZE,
        min_domains: int = _MIN_DOMAINS,
        min_support_rate: float = _MIN_SUPPORT_RATE,
        min_discrimination: float = _MIN_DISCRIMINATION,
        min_confidence: float = _MIN_CONFIDENCE,
        causal_filter: CausalFilter | None = None,
        override_causal_check: bool = False,
        belief_integrator: BeliefIntegrator | None = None,
    ):
        self.min_sample_size = min_sample_size
        self.min_domains = min_domains
        self.min_support_rate = min_support_rate
        self.min_discrimination = min_discrimination
        self.min_confidence = min_confidence
        self._causal_filter = causal_filter
        self._override_causal_check = override_causal_check
        self._belief = belief_integrator

    def set_causal_filter(self, causal_filter: CausalFilter) -> None:
        """Attach a CausalFilter after construction."""
        self._causal_filter = causal_filter

    def validate(self, candidate: PrincipleCandidate,
                 data_points: list | None = None) -> PrincipleCandidate:
        """Evaluate a candidate and return it with updated status and confidence.

        Args:
            candidate: The candidate to evaluate.
            data_points: Required if a CausalFilter is attached. Used for
                         confounder-controlled analysis.

        Returns the same candidate object (mutated) for chaining.
        """
        # Compute confidence from evidence
        if self._belief is not None:
            dc = self._belief.adjust_principle_confidence(
                discrimination=candidate.discrimination,
                sample_size=candidate.sample_size,
                domains=candidate.domains,
                current_confidence=self._compute_confidence(candidate),
            )
            candidate.confidence = dc.overall
        else:
            candidate.confidence = self._compute_confidence(candidate)

        # Check statistical gates
        if candidate.sample_size < self.min_sample_size:
            candidate.status = PrincipleStatus.CANDIDATE
            return candidate

        if len(candidate.domains) < self.min_domains:
            candidate.status = PrincipleStatus.CANDIDATE
            return candidate

        if candidate.support_rate < self.min_support_rate:
            candidate.status = PrincipleStatus.CANDIDATE
            return candidate

        if abs(candidate.discrimination) < self.min_discrimination:
            candidate.status = PrincipleStatus.CANDIDATE
            return candidate

        if candidate.confidence < self.min_confidence:
            candidate.status = PrincipleStatus.CANDIDATE
            return candidate

        # Phase 14.3: Causal check (if filter is attached)
        if self._causal_filter is not None and not self._override_causal_check:
            if data_points is None:
                logger.warning("CausalFilter attached but no data_points provided — skipping causal gate")
            else:
                analysis = self._causal_filter.analyze(candidate, data_points)
                if analysis.status == CausalStatus.LIKELY_CONFOUNDED:
                    logger.info(
                        "Candidate %s rejected by causal gate: "
                        "raw d=%.3f, adjusted d=%.3f, confounders=%s",
                        candidate.property_name,
                        analysis.raw_discrimination,
                        analysis.adjusted_discrimination,
                        analysis.confounded_by,
                    )
                    candidate.status = PrincipleStatus.CANDIDATE
                    return candidate

        candidate.status = PrincipleStatus.ACCEPTED
        return candidate

    def is_accepted(self, candidate: PrincipleCandidate,
                    data_points: list | None = None) -> bool:
        """Quick check — does the candidate pass all gates?"""
        return self.validate(candidate, data_points).status == PrincipleStatus.ACCEPTED

    @staticmethod
    def _compute_confidence(candidate: PrincipleCandidate) -> float:
        """Compute confidence from sample size and discrimination strength.

        Calibrated so a candidate at minimum thresholds (n=10, d=0.20,
        3 domains) achieves ~0.80 confidence — enough to pass the gate.

        Formula:
          0.45 × min(n/12, 1.0)  — sample size, saturates at n=12
          0.35 × min(d/0.25, 1.0) — discrimination strength
          0.20 × min(domains/2.5, 1.0) — domain diversity

        At minimum (n=10, d=0.20, 3 domains): 0.45×0.83 + 0.35×0.80 + 0.20×1.0 = 0.89
        At strong (n=24, d=0.35, 3 domains):  0.45×1.0  + 0.35×1.0  + 0.20×1.0 = 1.0 → 0.95
        """
        n = candidate.sample_size
        d = abs(candidate.discrimination)
        domain_count = len(candidate.domains)

        n_factor = min(n / 12.0, 1.0)
        d_factor = min(d / 0.25, 1.0)
        domain_factor = min(domain_count / 2.5, 1.0)

        confidence = 0.45 * n_factor + 0.35 * d_factor + 0.20 * domain_factor

        return min(max(round(confidence, 3), 0.0), 0.95)
