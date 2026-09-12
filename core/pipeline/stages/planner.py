"""Module: core.pipeline.stages.planner
Planner stage that uses the SPCL-6 PlannerExecutor for goal decomposition,
execution graph building, and failure-driven replanning.

This is the core integration point that uses the SPCL-6 planner intelligence
rather than creating a separate planning mechanism.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.planner.evidence import PlannerEvidence, FailureEvidence
from core.planner.executor import PlannerExecutor
from core.planner.outcomes import determine_outcome, PlannerOutcome
from core.planner.state_machine import PlannerStateMachine, PlannerStateName


class PlannerStage(PipelineStage):
    """Stage that uses the SPCL-6 PlannerExecutor for goal decomposition,
    execution graph building, and failure-driven replanning.

    Key behaviors:
    - Decomposes the user's intent goal into sub-goals
    - Builds an execution graph with dependency information
    - Executes steps with failure detection via mark_failed()
    - Triggers replanning when sub-goals fail
    - Selects alternate strategies when primary path fails
    - Records complete evidence for every replanning decision

    This stage is the primary integration point between the pipeline
    and the SPCL-6 Planner Intelligence.
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Execute planning using the SPCL-6 PlannerExecutor.

        The planner:
        1. Decomposes the intent goal into sub-goals
        2. Builds an execution graph with dependencies
        3. Executes steps, detecting failures via mark_failed()
        4. ReplanS on failure with alternate strategies
        5. Records complete evidence for replanning decisions
        6. Returns SUCCESS, FAILURE, or UNCONFIRMED based on verification
        """
        # Retrieve planning state from context
        metadata = getattr(context, "metadata", {}) or {}
        sub_goals = metadata.get("sub_goals", [])
        execution_graph_data = metadata.get("execution_graph", None)

        # Create the SPCL-6 PlannerExecutor
        planner = PlannerExecutor(max_parallel=3)

        # Reset planner state for this execution
        planner = PlannerExecutor(max_parallel=3)

        intent_goal = getattr(context, "metadata", {}).get("intent_goal", "")
        if not intent_goal:
            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                error="No intent goal available for planning",
                metadata={"planning_status": "no_intent_goal"},
            )

        # Decompose the goal into sub-goals
        sub_goals = planner.decompose_goal(intent_goal)
        execution_graph = planner.build_execution_graph(sub_goals)

        # Mark planning as started in state machine
        planner.state_machine.transition(PlannerStateName.RUNNING)

        # Execute the workflow with failure detection and replanning
        result = await planner.execute_workflow(intent_goal, agent_execute=None)

        # Determine the final outcome using the outcomes module
        # The outcome integrates success, verification, and replanning status
        planning_success = result.status == PlannerOutcome.SUCCESS
        replanned = result.replanned or (
            result.failure_evidence is not None
        )

        # Determine final outcome
        final_outcome = determine_outcome(
            success=planning_success,
            verified=bool(result.artifacts),
            replanned=replanned,
        )

        # Store comprehensive planning results in context
        new_metadata = dict(metadata)
        new_metadata["planning_status"] = final_outcome.value
        new_metadata["planner_final_state"] = result.final_state
        new_metadata["planner_replanned"] = replanned
        new_metadata["planner_outcome"] = final_outcome.value
        new_metadata["planning_artifacts"] = dict(result.artifacts) if result.artifacts else {}
        new_metadata["planning_error"] = result.error or ""
        new_metadata["sub_goals"] = sub_goals

        # Store comparison and verification evidence if available
        if result.comparison_evidence:
            new_metadata["comparison_ranking"] = [
                {"strategy": sid, "score": score}
                for sid, score in result.comparison_evidence.ranking
            ]
            new_metadata["comparison_selected"] = result.comparison_evidence.selected_strategy_id or ""
        if result.verification_evidence:
            new_metadata["verification_status"] = result.verification_evidence.verification_status
            new_metadata["verification_details"] = result.verification_evidence.verification_details

        # Update context metadata
        context.metadata = new_metadata

        # Return stage result based on the final outcome
        outcome_map = {
            PlannerOutcome.SUCCESS: StageOutcome.CONTINUE,
            PlannerOutcome.FAILURE: StageOutcome.FAIL,
            PlannerOutcome.UNCONFIRMED: StageOutcome.SHORT_CIRCUIT,
            PlannerOutcome.REPLANNED: StageOutcome.CONTINUE,
        }

        final_stage_outcome = outcome_map.get(final_outcome, StageOutcome.CONTINUE)

        return StageResult(
            outcome=final_stage_outcome,
            context=context,
            metadata={
                "planning_status": final_outcome.value,
                "planner_replanned": replanned,
                "planner_outcome": final_outcome.value,
                "sub_goals_count": len(sub_goals),
                "final_state": result.final_state,
            },
            error=result.error,
        )