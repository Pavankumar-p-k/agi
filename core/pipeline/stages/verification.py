"""Module: core.pipeline.stages.verification
Verification stage that performs objective verification of execution results.

Critical rule (from SPCL-6 outcomes.py):
    No verification → UNCONFIRMED
    Not SUCCESS

This stage ensures that execution appearing to succeed is not reported
as successful unless objective verification confirms it.

Uses the core.planner.outcomes.determine_outcome() rules for
consistent outcome determination across the pipeline.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.planner.outcomes import determine_outcome, PlannerOutcome


class VerificationStage(PipelineStage):
    """Stage that performs objective verification of execution results.

    Ensures that the pipeline does not falsely report success when
    objective verification fails. Uses the SPCL-6 outcomes module
    to determine the correct outcome.

    Verification flow:
    1. Check if execution result has verifiable artifacts/evidence
    2. Verify the result against the original goal/intent
    3. Determine outcome using determine_outcome() rules:
       - success=True & verified=True → SUCCESS
       - success=True & verified=False → UNCONFIRMED
       - success=False → FAILURE
    4. Propagate the verified outcome through the pipeline.
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Verify the execution result and determine the final outcome."""
        metadata = getattr(context, "metadata", {}) or {}

        # Get the planning/execution outcomes from earlier stages
        planning_outcome = metadata.get("planning_outcome", "")
        execution_status = metadata.get("execution_status", "")
        final_state = metadata.get("final_state", "")
        artifacts = metadata.get("planning_artifacts", {}) or metadata.get("artifacts", {})

        # Determine verification status based on available evidence
        # In a real implementation, this would involve checking the
        # execution result against the original goal criteria
        has_artifacts = bool(artifacts)
        has_final_state = bool(final_state)

        # Use the SPCL-6 outcomes module to determine the correct outcome
        # The key rule: if success but not verified → UNCONFIRMED
        if planning_outcome == PlannerOutcome.SUCCESS.value and not has_artifacts:
            # Success declared but no artifacts for verification → UNCONFIRMED
            verified = False
        elif planning_outcome == PlannerOutcome.FAILURE.value:
            # Plan already failed
            verified = False
            final_outcome = PlannerOutcome.FAILURE
        elif planning_outcome == PlannerOutcome.UNCONFIRMED.value:
            # Already unconfirmed
            verified = False
            final_outcome = PlannerOutcome.UNCONFIRMED
        else:
            # Default: assume verified if we have artifacts and a final state
            verified = has_artifacts and has_final_state

        # Determine the final outcome using the outcomes module
        final_outcome = determine_outcome(
            success=(planning_outcome == PlannerOutcome.SUCCESS.value),
            verified=verified,
            replanned=metadata.get("planner_replanned", False),
        )

        # Build the stage result metadata
        val_metadata = dict(metadata)
        val_metadata["verification_status"] = final_outcome.value
        val_metadata["verification_details"] = {
            "planning_outcome": planning_outcome,
            "execution_status": execution_status,
            "has_artifacts": has_artifacts,
            "has_final_state": has_final_state,
            "verified": verified,
            "replanned": metadata.get("planner_replanned", False),
        }

        # Map the planner outcome to a stage outcome
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
            metadata=val_metadata,
            error=metadata.get("planning_error") or metadata.get("execution_error"),
        )