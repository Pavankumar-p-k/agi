"""Planner stage — currently a pass-through.

A full Planner implementation will decompose the goal into an executable
plan (sequence of tool calls, sub-agent invocations, or LLM interactions).
For now the stage simply records the raw input as the plan text.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class PlannerStage(PipelineStage):
    """Decompose the classified goal into an executable plan.

    **Invariant:** Never talks to transports, never accesses memory.
    Only reads ``context.classification`` and writes ``context.plan``.
    """

    @property
    def name(self) -> str:
        return "planner"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.plan = {
            "goal": context.raw_input,
            "steps": [],
        }
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
