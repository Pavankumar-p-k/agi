"""PlannerStage — canonical multi-strategy planner.

Generates, compares, and ranks multiple candidate plans before selecting
the best one.  Wraps ``core/research/planner.py`` as one strategy engine
among several.

Pipeline position: after Reasoning, before PlanValidator.
"""
from __future__ import annotations

import uuid
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.planner_result import (
    PlanRanking,
    PlannerResult,
    PlanningStrategy,
    StrategyComparison,
)


class PlannerStage(PipelineStage):
    """Multi-strategy planner.

    Generates 2–3 candidate strategies for each request:
      1. **Direct** — simple respond intent (for chat requests).
      2. **Research-driven** — search_web → respond (for research requests).
      3. **Code-first** — write_code → respond (for coding requests).

    Strategies are scored and ranked.  The winning strategy populates
    ``context.plan`` for backward compat.
    """

    @property
    def name(self) -> str:
        return "planner"

    async def execute(self, context: PipelineContext) -> StageResult:
        assessment = context.reasoning_assessment or {}
        raw_input = context.raw_input or ""
        reasoning = context.reasoning_result

        # Generate strategy candidates
        strategies = self._generate_strategies(raw_input, assessment, reasoning)

        # Score and rank
        ranked = self._rank_strategies(strategies)

        # Select winner
        selected = ranked.strategies[0] if ranked.strategies else None

        # Build PlannerResult
        plan_id = _make_plan_id(context.services)
        planner_result = PlannerResult(
            plan_id=plan_id,
            ranking=ranked,
            selected_strategy=selected,
            total_candidates=len(strategies),
        )

        context.planner_result = planner_result

        # Backward compat: populate context.plan from selected strategy
        if selected:
            context.plan = {
                "goal": raw_input,
                "steps": list(selected.steps),
            }

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    # ── Strategy generation ──────────────────────────────────────────────

    def _generate_strategies(
        self,
        raw_input: str,
        assessment: dict[str, Any],
        reasoning: Any,
    ) -> list[PlanningStrategy]:
        strategies: list[PlanningStrategy] = []

        requirements = assessment.get("requirements", [])

        # Always include a direct strategy
        strategies.append(self._direct_strategy(raw_input))

        if "research" in requirements:
            strategies.append(self._research_strategy(raw_input, assessment))
        elif "browser" in requirements:
            strategies.append(self._browse_strategy(raw_input))

        if "coding" in requirements:
            strategies.append(self._code_strategy(raw_input))

        # If we only have one strategy, add a generic fallback
        if len(strategies) < 2:
            strategies.append(self._balanced_strategy(raw_input, assessment))

        return strategies

    def _direct_strategy(self, raw_input: str) -> PlanningStrategy:
        return PlanningStrategy(
            strategy_id=_sid("direct"),
            name="direct",
            description="Direct response without research or code.",
            steps=(self._step("respond", f"Respond to: {raw_input[:200]}"),),
            confidence=0.7,
            rationale="Simple chat/QA request.",
        )

    def _research_strategy(
        self, raw_input: str, assessment: dict[str, Any],
    ) -> PlanningStrategy:
        constraints = {c: True for c in assessment.get("constraints", [])}
        return PlanningStrategy(
            strategy_id=_sid("research"),
            name="research",
            description="Research then respond with evidence-based answer.",
            steps=(
                self._step("search_web", f"Research: {raw_input[:200]}",
                           {**constraints, "task": "research"}),
                self._step("respond", f"Synthesize findings for: {raw_input[:200]}"),
            ),
            confidence=0.8,
            rationale="Request requires information gathering.",
        )

    def _browse_strategy(self, raw_input: str) -> PlanningStrategy:
        return PlanningStrategy(
            strategy_id=_sid("browse"),
            name="browse",
            description="Browse web pages and synthesize content.",
            steps=(
                self._step("browse_web", f"Browse: {raw_input[:200]}",
                           {"task": "browse"}),
                self._step("respond", f"Synthesize from browsing: {raw_input[:200]}"),
            ),
            confidence=0.6,
            rationale="Request requires browsing specific web content.",
        )

    def _code_strategy(self, raw_input: str) -> PlanningStrategy:
        return PlanningStrategy(
            strategy_id=_sid("code"),
            name="code",
            description="Write code then explain the implementation.",
            steps=(
                self._step("write_code", f"Implement: {raw_input[:200]}",
                           {"task": "coding"}),
                self._step("respond", f"Explain implementation for: {raw_input[:200]}"),
            ),
            confidence=0.75,
            rationale="Request requires code generation.",
        )

    def _balanced_strategy(
        self, raw_input: str, assessment: dict[str, Any],
    ) -> PlanningStrategy:
        constraints = {c: True for c in assessment.get("constraints", [])}
        return PlanningStrategy(
            strategy_id=_sid("balanced"),
            name="balanced",
            description="General-purpose plan combining research and response.",
            steps=(
                self._step("search_web", f"Gather context: {raw_input[:200]}",
                           {**constraints, "task": "research"}),
                self._step("respond", f"Synthesize and respond: {raw_input[:200]}",
                           constraints),
            ),
            confidence=0.5,
            rationale="Fallback balanced strategy.",
        )

    # ── Ranking ──────────────────────────────────────────────────────────

    def _rank_strategies(
        self, strategies: list[PlanningStrategy],
    ) -> PlanRanking:
        if not strategies:
            return PlanRanking()

        # Score each strategy based on confidence and step count
        scored = [(s, s.confidence * self._step_score_bonus(s)) for s in strategies]
        scored.sort(key=lambda x: x[1], reverse=True)

        ranked_strategies = tuple(s for s, _ in scored)
        comparisons: list[StrategyComparison] = []

        for i in range(len(scored) - 1):
            winner, winner_score = scored[i]
            loser, loser_score = scored[i + 1]
            margin = winner_score - loser_score
            comparisons.append(StrategyComparison(
                winner_id=winner.strategy_id,
                loser_id=loser.strategy_id,
                margin=margin,
                reasons=(_comparison_reason(winner, loser, margin),),
            ))

        selected = ranked_strategies[0]
        return PlanRanking(
            strategies=ranked_strategies,
            comparisons=tuple(comparisons),
            selected_id=selected.strategy_id,
            selection_rationale=(
                f"Strategy '{selected.name}' ranked first "
                f"(confidence={selected.confidence}, "
                f"steps={len(selected.steps)})."
            ),
        )

    def _step_score_bonus(self, strategy: PlanningStrategy) -> float:
        """Score bonus/penalty based on step count.
        More steps = more thorough but higher risk.
        """
        n = len(strategy.steps)
        if n == 0:
            return 0.5
        if n == 1:
            return 1.0
        if n == 2:
            return 0.95
        return 0.9

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _step(
        intent: str, objective: str, constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "intent": intent,
            "objective": objective,
            "constraints": constraints or {},
        }


def _sid(prefix: str) -> str:
    """Generate a strategy id with the given prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _make_plan_id(services: Any) -> str:
    """Generate a deterministic or random plan id."""
    raw = services.uuid4()
    if isinstance(raw, str):
        return f"pl_{raw[:24]}"
    return f"pl_{raw.hex[:24]}"


def _comparison_reason(
    winner: PlanningStrategy, loser: PlanningStrategy, margin: float,
) -> str:
    if margin > 0.5:
        return f"'{winner.name}' significantly outperforms '{loser.name}' (margin={margin:.2f})."
    if margin > 0.1:
        return f"'{winner.name}' moderately outperforms '{loser.name}' (margin={margin:.2f})."
    return f"Slight preference for '{winner.name}' over '{loser.name}' (margin={margin:.2f})."
