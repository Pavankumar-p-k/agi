"""Portfolio optimization for v2 strategies (Phase 15.2)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from core.strategy.v2.models import (
    PortfolioAllocation,
    ResourceBudget,
    StrategyCandidate,
    TradeoffAnalysis,
)


def _ratio(candidate: StrategyCandidate, analysis: TradeoffAnalysis) -> float:
    if candidate.implementation_cost <= 0:
        return float("inf") if analysis.net_utility > 0 else 0.0
    return analysis.net_utility / candidate.implementation_cost


class PortfolioOptimizer:
    """Select the best value/cost strategies within an effort budget."""

    def _eligible(self, candidates, analyses, budget):
        analysis_by_id = {a.strategy_id: a for a in (analyses or [])}
        pairs = []
        for candidate in candidates or []:
            analysis = analysis_by_id.get(candidate.strategy_id)
            if analysis is None:
                continue
            if analysis.net_utility < budget.min_utility_threshold:
                continue
            effort = candidate.implementation_cost * budget.effort_budget
            pairs.append((candidate, analysis, effort, _ratio(candidate, analysis)))
        pairs.sort(key=lambda item: item[3], reverse=True)
        return pairs

    def optimize(
        self,
        candidates: List[StrategyCandidate],
        analyses: List[TradeoffAnalysis],
        budget: ResourceBudget,
    ) -> PortfolioAllocation:
        pairs = self._eligible(candidates, analyses, budget)
        remaining = budget.effort_budget
        selected, selected_analyses = [], []
        deferred, deferred_analyses = [], []
        consumed = 0.0
        value = 0.0

        for candidate, analysis, effort, ratio in pairs:
            if effort <= remaining + 1e-9:
                selected.append(candidate)
                selected_analyses.append(analysis)
                remaining -= effort
                consumed += effort
                value += analysis.net_utility
            else:
                deferred.append(candidate)
                deferred_analyses.append(analysis)

        if selected:
            rationale = "Selected by value/cost ratio: " + ", ".join(
                f"{c.name} ({_ratio(c, a):.2f})"
                for c, a in zip(selected, selected_analyses)
            )
        else:
            rationale = "Nothing to allocate."

        return PortfolioAllocation(
            selected=selected,
            selected_analyses=selected_analyses,
            deferred=deferred,
            deferred_analyses=deferred_analyses,
            total_effort_consumed=consumed,
            total_expected_value=value,
            remaining_effort=remaining,
            rationale=rationale,
        )

    def select_best(
        self,
        candidates: List[StrategyCandidate],
        analyses: List[TradeoffAnalysis],
        budget: ResourceBudget,
    ) -> Optional[Tuple[StrategyCandidate, TradeoffAnalysis]]:
        pairs = self._eligible(candidates, analyses, budget)
        for candidate, analysis, effort, _ratio_value in pairs:
            if effort <= budget.effort_budget + 1e-9:
                return candidate, analysis
        return None
