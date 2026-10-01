"""Strategic planning from improvement proposals (Phase 15.1)."""
from __future__ import annotations

import uuid
from typing import Dict, List

from core.strategy.v2.models import StrategyCandidate

_COST_BY_TYPE = {
    "add_capability": 0.40,
    "modify_behavior": 0.30,
    "add_verification": 0.35,
    "optimize": 0.50,
}
_DEFAULT_COST = 0.40


def _impact_dimension(target_system: str) -> str:
    name = (target_system or "").lower()
    if "browser" in name:
        return "browser"
    if "coding" in name or "code" in name:
        return "coding"
    if "memory" in name:
        return "memory"
    if "research" in name:
        return "research"
    if "performance" in name or "perf" in name:
        return "performance"
    return "general"


class StrategicPlanner:
    """Turn proposals into single and combined strategy candidates."""

    def plan_from_proposals(self, proposals: List) -> List[StrategyCandidate]:
        if not proposals:
            return []

        candidates: List[StrategyCandidate] = []
        for proposal in proposals:
            candidates.append(self._single_candidate(proposal))

        by_system: Dict[str, List] = {}
        for proposal in proposals:
            by_system.setdefault(proposal.target_system, []).append(proposal)
        for system, grouped in by_system.items():
            if len(grouped) >= 2:
                candidates.append(self._combined_candidate(system, grouped))

        return candidates

    # ── internals ────────────────────────────────────────────────────

    def _single_candidate(self, proposal) -> StrategyCandidate:
        improvement = proposal.expected_improvement * proposal.confidence
        dimension = _impact_dimension(proposal.target_system)
        cost = _COST_BY_TYPE.get(proposal.proposal_type, _DEFAULT_COST)
        return StrategyCandidate(
            strategy_id=f"strat_{uuid.uuid4().hex[:12]}",
            name=f"Improve {proposal.target_system}",
            description=(
                f"{proposal.title} ({proposal.expected_improvement:.0%} "
                f"expected improvement)"
            ),
            proposal_ids=[proposal.proposal_id],
            impact_by_dimension={dimension: improvement, "general": improvement * 0.1},
            overall_improvement=improvement,
            risk=1.0 - proposal.confidence,
            implementation_cost=cost,
            confidence=proposal.confidence,
        )

    def _combined_candidate(self, system: str, proposals: List) -> StrategyCandidate:
        improvements = [
            p.expected_improvement * p.confidence for p in proposals
        ]
        confidence = sum(p.confidence for p in proposals) / len(proposals)
        # Combine gains with diminishing returns.
        combined = min(1.0, sum(improvements))
        dimension = _impact_dimension(system)
        cost = min(1.0, sum(
            _COST_BY_TYPE.get(p.proposal_type, _DEFAULT_COST) for p in proposals
        ) / len(proposals) * 1.2)
        return StrategyCandidate(
            strategy_id=f"strat_{uuid.uuid4().hex[:12]}",
            name=f"Combined {system} improvements",
            description=(
                " + ".join(p.title for p in proposals)
                + f" ({combined:.0%} expected improvement)"
            ),
            proposal_ids=[p.proposal_id for p in proposals],
            impact_by_dimension={dimension: combined, "general": combined * 0.1},
            overall_improvement=combined,
            risk=1.0 - confidence,
            implementation_cost=cost,
            confidence=confidence,
        )
