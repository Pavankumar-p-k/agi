"""PlannerStage — Rule 51 owner of PlanningStrategy/PlanRanking construction.

Deterministic strategy generation based on reasoning assessment:
  always            -> "direct"
  research required -> "research"
  coding required   -> "code"
  fallback          -> "balanced" (when only direct exists)
Ranking: highest estimated success first; pairwise comparisons recorded.
"""
from __future__ import annotations

import uuid as _uuid

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.planner_result import (
    PlannerResult,
    PlanRanking,
    PlanningStrategy,
    StrategyComparison,
)


def _strategy_defs(requirements: list) -> list[tuple]:
    defs = [("direct", 0.9, 1)]
    if any("research" in r for r in requirements):
        defs.append(("research", 0.8, 3))
    if any("coding" in r for r in requirements):
        defs.append(("code", 0.75, 4))
    if len(defs) == 1:
        defs.append(("balanced", 0.7, 2))
    return defs


class PlannerStage(PipelineStage):
    @property
    def name(self) -> str:
        return "planner"

    async def execute(self, context: PipelineContext) -> StageResult:
        services = getattr(context, "services", None)
        plan_id = services.uuid4() if services is not None and hasattr(services, "uuid4") \
            else _uuid.uuid4().hex

        assessment = getattr(context, "reasoning_assessment", None) or {}
        requirements = list(assessment.get("requirements", [])
                            if isinstance(assessment, dict) else [])

        strategies = [
            PlanningStrategy(name=n, confidence=c, estimated_steps=s,
                             requirements=tuple(requirements))
            for n, c, s in _strategy_defs(requirements)
        ]
        strategies.sort(key=lambda s: (-s.confidence, s.name))
        selected = strategies[0]

        comparisons = tuple(
            StrategyComparison(left=a.name, right=b.name, winner=a.name,
                               rationale=f"{a.name} confidence {a.confidence} >= "
                                         f"{b.name} confidence {b.confidence}")
            for i, a in enumerate(strategies)
            for b in strategies[i + 1:]
        )

        ranking = PlanRanking(
            strategies=tuple(strategies),
            selected_id=selected.name,
            selection_rationale=f"selected {selected.name} "
                                f"(confidence={selected.confidence})",
            comparisons=comparisons,
        )
        context.planner_result = PlannerResult(
            plan_id=plan_id,
            activity_id=getattr(context, "activity_id", "") or "",
            total_candidates=len(strategies),
            ranking=ranking,
        )

        # Backward-compat plan (dict form used by the ExecutionStage).
        goal = str(getattr(context, "raw_input", "") or "")
        context.plan = {
            "goal": goal,
            "steps": [
                {"intent": "respond" if selected.name == "direct" else selected.name,
                 "objective": goal,
                 "constraints": {}},
            ],
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["PlannerStage"]
