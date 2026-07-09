"""ReflectionStage — canonical post-execution reflection and pattern learning.

Adapts the existing ``core/research/reflection.py`` ResearchReflection
engine into the pipeline.

Pipeline position: after Epistemic, before Memory (Sprint 4).

Inputs from PipelineContext:
  - activity_id
  - raw_input
  - plan (or planner_result)
  - knowledge_result (facts count)
  - reasoning_result (contradictions count, beliefs)

Outputs:
  - context.reflection_result
"""
from __future__ import annotations

from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.reflection_result import ReflectionResult
from core.research.reflection import ResearchReflection


class ReflectionStage(PipelineStage):
    """Canonical reflection stage.

    Analyses completed activity data (plan, outcomes, knowledge,
    reasoning) and produces structured reflections with lessons
    and patterns.
    """

    def __init__(self, reflection_engine: ResearchReflection | None = None) -> None:
        self._engine = reflection_engine or ResearchReflection()

    @property
    def name(self) -> str:
        return "reflection"

    async def execute(self, context: PipelineContext) -> StageResult:
        activity_id = context.activity_id or ""
        question = context.raw_input or ""
        plan = context.plan or {}
        reasoning = context.reasoning_result
        knowledge = context.knowledge_result

        # Build plan summary from pipeline artifacts
        plan_summary = self._build_plan_summary(plan, reasoning, knowledge)

        # Extract facts count and coverage data
        facts_count = knowledge.node_count if knowledge else 0

        # Build a minimal coverage-like structure from reasoning result
        coverage = self._build_coverage(reasoning) if reasoning else None

        # Run reflection engine
        engine_result = self._engine.analyze(
            activity_id=activity_id,
            question=question,
            plan_summary=plan_summary,
            facts_count=facts_count,
            coverage=coverage,
        )

        # Map to pipeline's frozen ReflectionResult
        reflection_result = ReflectionResult(
            reflection_id=engine_result.reflection_id,
            activity_id=engine_result.activity_id,
            question=engine_result.question,
            strategies_used=tuple(engine_result.strategies_used),
            total_facts_collected=engine_result.total_facts_collected,
            total_sources=engine_result.total_sources,
            goals_answered=engine_result.goals_answered,
            goals_total=engine_result.goals_total,
            contradictions_found=engine_result.contradictions_found,
            overall_confidence=engine_result.overall_confidence,
            iterations_needed=engine_result.iterations_needed,
            success_rating=engine_result.success_rating,
            lessons=tuple(engine_result.lessons),
            patterns=tuple(engine_result.patterns),
        )

        context.reflection_result = reflection_result

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _build_plan_summary(
        self,
        plan: dict[str, Any],
        reasoning: Any,
        knowledge: Any,
    ) -> dict[str, Any]:
        """Build a plan_summary dict for the reflection engine."""
        contradictions = 0
        if reasoning:
            contradictions = len(reasoning.contradictions)
        return {
            "contradictions_found": contradictions,
            "iteration": 1,
            "goal": plan.get("goal", ""),
            "steps": plan.get("steps", []),
        }

    def _build_coverage(self, reasoning: Any) -> Any:
        """Build a duck-typed coverage object from ReasoningResult."""
        from types import SimpleNamespace

        beliefs = reasoning.beliefs or []
        contradictions = reasoning.contradictions or []

        return SimpleNamespace(
            total_facts=len(beliefs),
            covered_goals=len([b for b in beliefs if b.status == "accepted"]),
            total_goals=max(len(contradictions), 1),
            overall_confidence=reasoning.confidence,
        )
