"""Proposal prioritization (Phase 14.2)."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple


class ProposalPrioritizer:
    """Rank proposals by expected value times applicability."""

    def __init__(
        self, applicability_fn: Optional[Callable] = None
    ) -> None:
        self.applicability_fn = applicability_fn

    def _applicability(self, proposal) -> float:
        if self.applicability_fn is not None:
            try:
                return float(self.applicability_fn(proposal))
            except Exception:
                return 1.0
        return 1.0

    def score(self, proposal) -> float:
        return (
            proposal.expected_improvement
            * proposal.confidence
            * self._applicability(proposal)
        )

    def rank(
        self, proposals: List, max_results: int = 10
    ) -> List[Tuple[object, float]]:
        scored = [(p, self.score(p)) for p in (proposals or [])]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        if max_results and max_results > 0:
            return scored[:max_results]
        return scored

    @staticmethod
    def domain_count_applicability(proposal, domain_count: int) -> float:
        return min(1.0, max(0, domain_count) / 3.0)
