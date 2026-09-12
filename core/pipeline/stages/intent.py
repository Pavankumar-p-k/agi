"""Module: core.pipeline.stages.intent
Intent detection stage that extracts user intent from the request context.

Reuses the SPCL-6 planner infrastructure for goal decomposition
and routes to the planner stage for further processing.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.planner.executor import PlannerExecutor
from core.planner.outcomes import determine_outcome, PlannerOutcome


class IntentStage(PipelineStage):
    """Stage that detects and classifies user intent from the request.

    Extracts the core goal/intent from the pipeline context and
    prepares it for the reasoning/planning pipeline.
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Extract intent from the raw input stored in context."""
        raw = getattr(context, "raw_input", None) or getattr(context, "state", {}).get("raw_input", "")
        if not raw:
            # No input available - continue but mark need for input
            return StageResult(
                outcome=StageOutcome.SHORT_CIRCUIT,
                context=context,
                metadata={"intent_status": "no_input"},
            )

        # Basic intent extraction - in production would use LLM or NLP
        # For now, pass the raw goal through to the next stage
        intent_goal = raw.strip() if isinstance(raw, str) else str(raw)

        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=context,
            metadata={
                "intent_status": "detected",
                "intent_goal": intent_goal,
                "intent_source": "raw_input",
            },
        )