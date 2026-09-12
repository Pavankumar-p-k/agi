"""Module: core.pipeline.stages.load_context
Loads the pipeline context from the raw input request.

This stage is the second step in the 9-stage pipeline:
  ReceiveStage → LoadContextStage → IntentStage → ReasonerStage →
  PlannerStage → PlanValidatorStage → ExecutionStage → VerificationStage →
  FormatterStage

It extracts structured information from the raw CLI/API request and
initializes the PipelineContext for downstream processing.
"""

from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class LoadContextStage(PipelineStage):
    """Stage that loads and validates the pipeline context from the raw request.

    This stage:
    - Extracts the raw input from the request
    - Validizes the input format
    - Initializes a PipelineContext with the request information
    - Passes the context down the stage chain for intent detection

    The context is then processed by subsequent stages:
    intent → reasoner → planner → plan validator → execution → verification → formatter
    """

    async def execute(self, context: PipelineContext) -> StageResult:
        """Load and validate the pipeline context from the raw input."""
        raw_input = getattr(context, "raw_input", None)

        if not raw_input:
            return StageResult(
                outcome=StageOutcome.FAILURE,
                context=context,
                error="No raw input provided in context",
            )

        # Basic validation - ensure we have non-empty input
        if not raw_input or not raw_input.strip():
            return StageResult(
                outcome=StageOutcome.FAILURE,
                context=context,
                error="Empty raw input provided",
            )

        # Create a validated context with the extracted information
        # Preserve existing context fields and add extracted data
        new_context = PipelineContext(
            raw_input=raw_input,
            request_id=getattr(context, "request_id", "unknown"),
            classification=getattr(context, "classification", None),
            metadata=dict(getattr(context, "metadata", {})),
            identity=getattr(context, "identity", None),
            authorization_result=getattr(context, "authorization_result", None),
            services=getattr(context, "services", None),
            state=dict(getattr(context, "state", {})),
            pipeline_version=getattr(context, "pipeline_version", "1.0"),
            activity_id=getattr(context, "activity_id", ""),
            execution_state=getattr(context, "execution_state", "pending"),
        )

        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=new_context,
        )