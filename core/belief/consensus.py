"""Cross-source corroboration scoring for the Belief Quality Engine."""
from __future__ import annotations

from typing import Iterable, List, Optional


def _unique(values: Optional[Iterable[str]]) -> List[str]:
    seen = []
    for value in values or []:
        if value not in seen:
            seen.append(value)
    return seen


class ConsensusScorer:
    """Score how much independent sources agree on a belief."""

    SINGLE_SUPPORT = 0.55
    SINGLE_CONTRADICT = 0.35

    def score(
        self,
        supporting_sources: Optional[List[str]] = None,
        contradicting_sources: Optional[List[str]] = None,
    ) -> float:
        support = _unique(supporting_sources)
        contradict = _unique(contradicting_sources)

        # Remove overlap — a source cannot support both sides.
        overlap = set(support) & set(contradict)
        if overlap:
            support = [s for s in support if s not in overlap]
            contradict = [c for c in contradict if c not in overlap]

        s, c = len(support), len(contradict)
        n = s + c
        if n == 0:
            return 1.0
        if n == 1:
            return self.SINGLE_SUPPORT if s == 1 else self.SINGLE_CONTRADICT

        agreement = (s - c) / n
        damping = n / (n + 1.0)
        value = 0.5 + 0.5 * agreement * damping
        return max(0.0, min(1.0, value))

    def score_from_fact_sets(
        self,
        supporting_fact_sources: Optional[List[List[str]]] = None,
        contradicting_fact_sources: Optional[List[List[str]]] = None,
    ) -> float:
        support: List[str] = []
        for fact in supporting_fact_sources or []:
            support.extend(fact or [])
        contradict: List[str] = []
        for fact in contradicting_fact_sources or []:
            contradict.extend(fact or [])
        return self.score(support, contradict)

    def dimension_name(self) -> str:
        return "consensus"

    def dimension_summary(self, score: float) -> str:
        if score >= 0.75:
            label = "strong"
        elif score >= 0.50:
            label = "moderate"
        elif score >= 0.35:
            label = "weak"
        else:
            label = "contested"
        return f"{label} consensus ({score:.2f})"
