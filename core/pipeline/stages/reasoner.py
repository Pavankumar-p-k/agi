"""Module: core.pipeline.stages.reasoner
Reasoning stage that processes user intent and determines the planning approach.

Connects intent detection to the SPCL-6 planner, enabling:
    intent → reasoning → planning integration

Uses the existing planner/executor infrastructure from SPCL-6.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.planner.executor import PlannerExecutor
from core.planner.outcomes import determine_outcome, PlannerOutcome


class ReasonerStage(PipelineStage):
    """Stage that reasons about the detected intent and prepares for planning.

    Takes the extracted intent goal and uses the SPCL-6 planner infrastructure
    to decompose the goal into sub-goals and build an execution graph.
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Reason about the intent and prepare planning."""
        intent_goal = getattr(context, "metadata", {}).get("intent_goal", "")
        context_metadata = getattr(context, "metadata", {}) or {}

        if not intent_goal:
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="No intent goal available for reasoning",
                metadata={"reasoning_status": "no_goal"},
            )

        # Use the SPCL-6 planner executor to decompose the goal
        planner = PlannerExecutor(max_parallel=3)

        try:
            # Decompose the goal into sub-goals
            sub_goals = planner.decompose_goal(intent_goal)
            execution_graph = planner.build_execution_graph(sub_goals)

            # Store planning results in context metadata for downstream stages
            new_metadata = dict(context_metadata)
            new_metadata["sub_goals"] = sub_goals
            new_metadata["execution_graph"] = (
                execution_graph.to_dict()
                if hasattr(execution_graph, "to_dict")
                else str(execution_graph)
            )
            new_metadata["planning_status"] = "decomposed"

            # Update context metadata
            context.metadata = new_metadata

            return StageResult(
                outcome=StageOutcome.CONTINUE,
                context=context,
                metadata={
                    "reasoning_status": "goal_decomposed",
                    "sub_goals_count": len(sub_goals),
                    "planning_status": "decomposed",
                },
            )

        except Exception as exc:
            # Planning failure - record error and propagate
            new_metadata = dict(context_metadata)
            new_metadata["planning_status"] = "failed"
            new_metadata["planning_error"] = str(exc)

            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error=str(exc),
                metadata={
                    "reasoning_status": "planning_failed",
                    "planning_error": str(exc),
                },
            )