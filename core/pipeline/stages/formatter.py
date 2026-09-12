"""Module: core.pipeline.stages.formatter
Formatter stage that formats the final pipeline result for user consumption.

 Takes the verified pipeline state and produces a clean, structured
 final result suitable for CLI or API response. Ensures that the
 output reflects the actual verified outcome (SUCCESS / UNCONFIRMED /
 FAILURE) rather than any intermediate state.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class FormatterStage(PipelineStage):
    """Stage that formats the final pipeline result for user consumption.

    Takes the verified context and produces a structured final result
    that reflects the actual pipeline outcome. Handles the transformation
    from internal pipeline state to user-facing result format.

    Key behaviors:
    - Maps pipeline StageOutcome to result status
    - Extracts relevant artifacts and evidence from context metadata
    - Produces a clean result dict suitable for API/CLI response
    - Ensures the reported outcome matches the verified outcome
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Format the final pipeline result."""
        metadata = getattr(context, "metadata", {}) or {}

        # Get the verified outcome from earlier stages
        verification_status = metadata.get("verification_status", "unknown")
        planning_outcome = metadata.get("planning_outcome", "")
        execution_status = metadata.get("execution_status", "")
        artifacts = metadata.get("planning_artifacts", {}) or metadata.get("artifacts", {})

        # Build the user-facing result
        result: dict[str, Any] = {
            "status": verification_status,
            "planning_outcome": planning_outcome,
            "execution_status": execution_status,
            "has_artifacts": bool(artifacts),
            "artifact_count": len(artifacts) if artifacts else 0,
        }

        # Add artifacts summary if available
        if artifacts:
            result["artifacts_summary"] = {
                k: v for k, v in list(artifacts.items())[:10]
            }  # First 10 artifacts

        # Add execution summary
        if execution_status:
            result["execution_summary"] = execution_status

        # Map the final stage outcome
        outcome_map = {
            StageOutcome.CONTINUE: "success",
            StageOutcome.FAIL: "failure",
            StageOutcome.SHORT_CIRCUIT: "unconfirmed",
        }
        result["pipeline_status"] = outcome_map.get(
            context._pipeline_stage_result_outcome if hasattr(context, "_pipeline_stage_result_outcome") else StageOutcome.CONTINUE,
            "unknown",
        )

        # Store the formatted result in context metadata for downstream
        result_metadata = dict(metadata)
        result_metadata["formatted_result"] = result
        result_metadata["formatter_status"] = verification_status

        # Update context metadata
        context.metadata = result_metadata

        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=context,
            metadata=result_metadata,
        )