"""Phase 14.2 — Proposal Prioritizer.

Ranks improvement proposals by expected value.

With many accepted principles × many systems, the number of proposals
can grow large. The prioritizer surfaces only the highest-value ones.

Priority formula:
    score = expected_improvement × confidence × applicability
"""

from __future__ import annotations

import logging
from typing import Any

from core.generalization.models import ImprovementProposal

logger = logging.getLogger(__name__)

# Default applicability for proposals where no system-specific factor is known
_DEFAULT_APPLICABILITY = 1.0


class ProposalPrioritizer:
    """Ranks ImprovementProposals by expected value.

    Deterministic scoring — no LLM, no random tie-breaking.
    """

    def __init__(self, applicability_fn=None):
        """Args:
            applicability_fn: Optional callable (proposal) -> float.
                              If None, uses DEFAULT_APPLICABILITY.
        """
        self._applicability_fn = applicability_fn

    def rank(
        self,
        proposals: list[ImprovementProposal],
        max_results: int = 10,
    ) -> list[tuple[ImprovementProposal, float]]:
        """Rank proposals by priority score, highest first.

        Args:
            proposals: Unordered proposals to rank.
            max_results: Maximum number to return (0 = all).

        Returns:
            List of (proposal, score) tuples sorted descending by score.
        """
        scored = [(p, self._score(p)) for p in proposals]
        scored.sort(key=lambda x: -x[1])

        if max_results > 0 and len(scored) > max_results:
            scored = scored[:max_results]

        return scored

    def _score(self, proposal: ImprovementProposal) -> float:
        """Compute priority score for a single proposal."""
        applicability = (
            self._applicability_fn(proposal)
            if self._applicability_fn
            else _DEFAULT_APPLICABILITY
        )
        return proposal.expected_improvement * proposal.confidence * applicability

    @staticmethod
    def domain_count_applicability(proposal: ImprovementProposal,
                                    principle_domain_count: int) -> float:
        """Compute applicability from the principle's domain breadth.

        A principle validated across more domains applies to more contexts,
        making its proposal more valuable.
        """
        return min(principle_domain_count / 3.0, 1.0)
