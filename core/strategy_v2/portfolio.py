"""Phase 15.2 — Resource-Constrained Portfolio Optimizer.

Before Phase 15.2:
    Strategies ranked by utility → pick the best one

After Phase 15.2:
    Strategies ranked by value/cost within budget → pick the optimal set
    → execute now → defer the rest for later

This is the difference between:
    "Which improvement should I make?"
    "Which improvements should I make, given I have 2 weeks?"

The optimizer uses a greedy knapsack approach:
    sort by value/cost ratio → take until budget exhausted

This is intentionally simple (not full DP knapsack) for three reasons:
    1. Strategies are not independent (combined strategies create synergy)
    2. Greedy is more explainable for an autonomous system
    3. The effort estimates are approximate anyway
"""

from __future__ import annotations

import logging
from typing import Any

from core.strategy_v2.models import (
    PortfolioAllocation,
    ResourceBudget,
    StrategyCandidate,
    TradeoffAnalysis,
)

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """Resource-constrained portfolio selection.

    Given a set of strategy candidates with tradeoff analyses and
    a resource budget, selects the optimal subset for execution.

    Flow:
        strategies = planner.plan_from_proposals(proposals)
        analyses = tradeoff.analyze_all(strategies)
        allocation = optimizer.optimize(strategies, analyses, budget)
        # allocation.selected → execute now
        # allocation.deferred → queue for later
    """

    def optimize(self,
                 candidates: list[StrategyCandidate],
                 analyses: list[TradeoffAnalysis],
                 budget: ResourceBudget | None = None,
                 ) -> PortfolioAllocation:
        """Select the optimal subset of strategies under resource constraints.

        Greedy knapsack algorithm:
            1. Pair candidates with analyses
            2. Filter out negative-utility strategies
            3. Sort by utility/cost ratio (value per unit effort)
            4. Take strategies until budget exhausted
            5. Remainder goes to deferred

        Args:
            candidates: Strategy candidates (from StrategicPlanner).
            analyses: Tradeoff analyses (from TradeoffEngine).
            budget: Resource budget. Defaults to 40 effort units.

        Returns:
            PortfolioAllocation with selected and deferred strategies.
        """
        budget = budget or ResourceBudget()

        if not candidates or not analyses:
            return self._empty_allocation(budget)

        # Build lookup: strategy_id → analysis
        analysis_map = {a.strategy_id: a for a in analyses}
        paired = [
            (c, analysis_map[c.strategy_id])
            for c in candidates
            if c.strategy_id in analysis_map
        ]

        if not paired:
            return self._empty_allocation(budget)

        # Separate zero-cost (always include) and positive-cost (must be prioritized)

        # Filter 1: exclude negative-utility below threshold
        filtered = [
            (c, a) for c, a in paired
            if a.net_utility >= budget.min_utility_threshold
        ]

        # Split zero-cost and positive-cost
        zero_cost = [(c, a) for c, a in filtered if c.implementation_cost <= 0.0]
        positive_cost = [(c, a) for c, a in filtered if c.implementation_cost > 0.0]

        # Sort positive-cost by value/cost ratio descending
        positive_cost.sort(
            key=lambda x: x[1].net_utility / x[0].implementation_cost,
            reverse=True,
        )

        # Greedy knapsack
        selected: list[StrategyCandidate] = []
        selected_analyses: list[TradeoffAnalysis] = []
        deferred: list[StrategyCandidate] = []
        deferred_analyses: list[TradeoffAnalysis] = []
        remaining = budget.effort_budget

        # Zero-cost strategies always go in (they cost nothing)
        for c, a in zero_cost:
            selected.append(c)
            selected_analyses.append(a)

        # Positive-cost strategies compete for the rest
        for c, a in positive_cost:
            effort = c.implementation_cost * budget.effort_budget
            if effort <= remaining:
                selected.append(c)
                selected_analyses.append(a)
                remaining -= effort
            else:
                deferred.append(c)
                deferred_analyses.append(a)

        total_value = sum(
            a.net_utility for a in selected_analyses
        )
        total_effort = budget.effort_budget - remaining

        rationale = self._build_rationale(
            selected, selected_analyses,
            deferred, deferred_analyses,
            total_effort, total_value, remaining, budget,
        )

        return PortfolioAllocation(
            selected=selected,
            selected_analyses=selected_analyses,
            deferred=deferred,
            deferred_analyses=deferred_analyses,
            total_effort_consumed=total_effort,
            total_expected_value=total_value,
            remaining_effort=remaining,
            rationale=rationale,
        )

    def select_best(self,
                    candidates: list[StrategyCandidate],
                    analyses: list[TradeoffAnalysis],
                    budget: ResourceBudget | None = None,
                    ) -> tuple[StrategyCandidate, TradeoffAnalysis] | None:
        """Convenience: select exactly one best strategy under budget.

        Returns the highest-value strategy that fits within budget.
        Useful when max_concurrent=1 or when only one should run at a time.

        Returns (candidate, analysis) or None if nothing fits.
        """
        budget = budget or ResourceBudget()
        allocation = self.optimize(candidates, analyses, budget)
        if allocation.selected:
            return allocation.selected[0], allocation.selected_analyses[0]
        return None

    # ── Helpers ─────────────────────────────────────────────────

    def _build_rationale(
        self,
        selected: list[StrategyCandidate],
        selected_analyses: list[TradeoffAnalysis],
        deferred: list[StrategyCandidate],
        deferred_analyses: list[TradeoffAnalysis],
        total_effort: float,
        total_value: float,
        remaining: float,
        budget: ResourceBudget,
    ) -> str:
        """Build a structured rationale for the portfolio allocation."""
        parts = [
            f"Budget: {budget.effort_budget} units",
            f"Selected: {len(selected)} strategies",
            f"Effort consumed: {total_effort:.1f}/{budget.effort_budget}",
            f"Total expected value: {total_value:.3f}",
        ]

        if selected:
            parts.append("Selected strategies:")
            for c, a in zip(selected, selected_analyses):
                effort = c.implementation_cost * budget.effort_budget
                ratio = a.net_utility / max(c.implementation_cost, 0.001)
                ov = f", option_value={a.option_value:.3f}" if a.option_value > 0 else ""
                parts.append(
                    f"  {c.name}: utility={a.net_utility:.3f}, "
                    f"effort={effort:.1f}, value/cost={ratio:.2f}{ov}"
                )

        if deferred:
            parts.append(f"Deferred: {len(deferred)} strategies")
            for c, a in zip(deferred, deferred_analyses):
                effort = c.implementation_cost * budget.effort_budget
                ratio = a.net_utility / max(c.implementation_cost, 0.001)
                ov = f", option_value={a.option_value:.3f}" if a.option_value > 0 else ""
                parts.append(
                    f"  {c.name}: utility={a.net_utility:.3f}, "
                    f"effort={effort:.1f}, value/cost={ratio:.2f}{ov}"
                )

        if remaining > 0:
            parts.append(f"Remaining budget: {remaining:.1f} units")

        return "\n".join(parts)

    @staticmethod
    def _empty_allocation(budget: ResourceBudget) -> PortfolioAllocation:
        return PortfolioAllocation(
            selected=[],
            selected_analyses=[],
            deferred=[],
            deferred_analyses=[],
            total_effort_consumed=0.0,
            total_expected_value=0.0,
            remaining_effort=budget.effort_budget,
            rationale="No strategies to allocate.",
        )
