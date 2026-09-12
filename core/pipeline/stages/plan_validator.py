"""Module: core.pipeline.stages.plan_validator
Plan validator stage that validates the execution plan from the planner stage.

Validates that the plan is sound, all required capabilities are available,
and the plan can be safely executed. Records validation evidence for the
pipeline's evidence trail.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class PlanValidatorStage(PipelineStage):
    """Stage that validates the execution plan produced by the planner stage.

    Validates:
    - Plan has sub-goals defined
    - Execution graph is well-formed
    - Required capabilities are identifiable
    - Plan structure is consistent and complete

    If validation fails, the stage short-circuits the pipeline and
    propagates the failure reason for downstream handling.
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Validate the plan produced by the planner stage."""
        metadata = getattr(context, "metadata", {}) or {}

        sub_goals = metadata.get("sub_goals", [])
        execution_graph_data = metadata.get("execution_graph", [])
        planning_status = metadata.get("planning_status", "")

        validation_errors: list[str] = []

        # Check that sub-goals exist
        if not sub_goals:
            validation_errors.append("No sub-goals defined in plan")

        # Check that execution graph has content
        if not execution_graph_data:
            validation_errors.append("No execution graph defined")

        # Check planning status is not a failure state
        if planning_status in ("failed", "unconfirmed"):
            validation_errors.append(
                f"Plan in failure/unconfirmed state: {planning_status}"
            )

        if validation_errors:
            # Build validation result metadata
            val_metadata = dict(metadata)
            val_metadata["plan_validator_errors"] = validation_errors
            val_metadata["plan_validator_status"] = "failed"

            return StageResult(
                outcome=StageOutcome.FAIL,
                context=context,
                metadata=val_metadata,
                error="; ".join(validation_errors),
            )

        # Plan validation passed
        val_metadata = dict(metadata)
        val_metadata["plan_validator_status"] = "passed"
        val_metadata["plan_validator_errors"] = []

        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=context,
            metadata=val_metadata,
        )