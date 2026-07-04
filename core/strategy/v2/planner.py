"""Phase 15.1 — Strategic Planner.

Generates candidate strategies from open proposals, active experiments,
and system goals.

Each strategy is a bundle of one or more proposals that can be pursued
together or in sequence. The planner explores:
  - Single-proposal strategies (focus on one improvement)
  - Multi-proposal strategies (complementary improvements)
  - Sequencing strategies (order matters)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.generalization.models import ImprovementProposal, ProposalStatus
from core.generalization.store import PrincipleStore
from core.strategy.v2.models import (
    ImpactDimension,
    StrategyCandidate,
    StrategyStatus,
    TimeHorizon,
)

logger = logging.getLogger(__name__)

_DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "coding": 0.20,
    "research": 0.15,
    "memory": 0.15,
    "planning": 0.20,
    "browser": 0.10,
    "build": 0.10,
    "general": 0.10,
}


class StrategicPlanner:
    """Generates candidate strategies from proposals and system state.

    For each open (GENERATED/APPROVED) proposal, creates a StrategyCandidate.
    Also bundles compatible proposals into multi-proposal strategies.
    """

    def __init__(self, dimension_weights: dict[str, float] | None = None):
        self._weights = dimension_weights or dict(_DEFAULT_DIMENSION_WEIGHTS)

    def plan_from_proposals(
        self,
        proposals: list[ImprovementProposal],
        max_candidates: int = 20,
    ) -> list[StrategyCandidate]:
        """Generate candidate strategies from a list of proposals.

        Creates one strategy per proposal, plus a few combined strategies
        for compatible proposals.
        """
        candidates: list[StrategyCandidate] = []

        # Single-proposal strategies
        for proposal in proposals:
            candidate = self._proposal_to_candidate(proposal)
            candidates.append(candidate)

        # Multi-proposal strategies (for proposals targeting same system)
        by_system: dict[str, list[ImprovementProposal]] = {}
        for p in proposals:
            by_system.setdefault(p.target_system, []).append(p)

        for system_id, sys_proposals in by_system.items():
            if len(sys_proposals) < 2:
                continue
            combined = self._build_combined_strategy(system_id, sys_proposals)
            if combined:
                candidates.append(combined)

        # Cap
        if max_candidates and len(candidates) > max_candidates:
            candidates = candidates[:max_candidates]

        return candidates

    def _proposal_to_candidate(self, proposal: ImprovementProposal
                                ) -> StrategyCandidate:
        """Convert a single proposal into a strategy candidate."""
        prop_name = proposal.proposal_type

        # Infer impact dimensions from proposal type and target
        dimensions = self._infer_dimensions(proposal)

        # Overall improvement = expected_improvement * confidence
        overall = proposal.expected_improvement * proposal.confidence

        # Risk: inversely related to confidence
        risk = 1.0 - proposal.confidence

        # Cost: estimate from proposal type
        cost = self._estimate_cost(proposal)

        return StrategyCandidate(
            strategy_id=f"strat_{uuid.uuid4().hex[:12]}",
            name=f"Add {prop_name} to {proposal.target_system}",
            description=proposal.rationale,
            proposal_ids=[proposal.proposal_id],
            impact_by_dimension=dimensions,
            overall_improvement=overall,
            risk=risk,
            implementation_cost=cost,
            confidence=proposal.confidence,
            time_horizon=TimeHorizon.SHORT_TERM,
            status=StrategyStatus.CANDIDATE,
        )

    def _build_combined_strategy(
        self,
        system_id: str,
        proposals: list[ImprovementProposal],
    ) -> StrategyCandidate | None:
        """Build a combined strategy for multiple proposals on the same system."""
        if len(proposals) < 2:
            return None

        combined_desc = f"Multi-improvement for {system_id}: "
        combined_desc += ", ".join(p.proposal_type for p in proposals)

        # Aggregate dimensions and scores
        all_dims: dict[str, list[float]] = {}
        total_improvement = 0.0
        total_confidence = 0.0
        total_risk = 0.0
        total_cost = 0.0

        for p in proposals:
            dims = self._infer_dimensions(p)
            for d, val in dims.items():
                all_dims.setdefault(d, []).append(val)

            improvement = p.expected_improvement * p.confidence
            total_improvement += improvement
            total_confidence += p.confidence
            total_risk += 1.0 - p.confidence
            total_cost += self._estimate_cost(p)

        n = len(proposals)
        avg_dims = {d: sum(vals) / n for d, vals in all_dims.items()}

        return StrategyCandidate(
            strategy_id=f"strat_{uuid.uuid4().hex[:12]}",
            name=f"Combined improvements for {system_id}",
            description=combined_desc,
            proposal_ids=[p.proposal_id for p in proposals],
            impact_by_dimension=avg_dims,
            overall_improvement=total_improvement / n,
            risk=total_risk / n,
            implementation_cost=total_cost / n,
            confidence=total_confidence / n,
            time_horizon=TimeHorizon.MEDIUM_TERM,
            status=StrategyStatus.CANDIDATE,
        )

    @staticmethod
    def _infer_dimensions(proposal: ImprovementProposal) -> dict[str, float]:
        """Infer which impact dimensions a proposal affects and by how much."""
        target = proposal.target_system.lower()
        prop_type = proposal.proposal_type.lower()

        base = proposal.expected_improvement

        mapping: dict[str, list[str]] = {
            "coding": ["coding", "refactor", "change", "edit", "code"],
            "research": ["research", "fact", "knowledge", "source"],
            "memory": ["memory", "store", "knowledge", "experience"],
            "planning": ["plan", "strategy", "decompose", "route"],
            "browser": ["browser", "navigate", "snapshot", "web"],
            "build": ["build", "compile", "repair", "test"],
            "collaboration": ["collaborat", "agent", "negotiate", "consensus"],
            "general": [],
        }

        result: dict[str, float] = {}
        for dim, keywords in mapping.items():
            if any(k in target or k in prop_type for k in keywords):
                result[dim] = base
            else:
                result[dim] = base * 0.1  # small spillover

        return result

    @staticmethod
    def _estimate_cost(proposal: ImprovementProposal) -> float:
        """Estimate implementation cost from proposal type."""
        cost_map = {
            "add_capability": 0.4,
            "enable_feature": 0.3,
            "refactor": 0.6,
            "redesign": 0.8,
            "optimize": 0.5,
        }
        return cost_map.get(proposal.proposal_type, 0.5)
