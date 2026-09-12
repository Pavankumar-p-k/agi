"""Module: core.pipeline.stages.receive
Receive stage that captures the incoming CLI/API request and initializes
the pipeline context for downstream processing.

This is the entry point of the pipeline - it receives the raw request,
parses it, and passes it down the stage chain for intent detection,
reasoning, planning, execution, verification, and formatting.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class ReceiveStage(PipelineStage):
    """Stage that receives the initial CLI/API request and initializes
    the pipeline context.

    This is the entry point of the pipeline. It:
    - Extracts the raw input from the request
    - Initializes a PipelineContext with the request information
    - Passes the context down the stage chain for further processing

    The context is then processed by subsequent stages:
    load_context → intent → reasoner → planner → plan_validator → execution → verification → formatter
    """

    async def execute(self, request: Any) -> StageResult:
        """Receive and initialize the pipeline context from the request."""
        # Extract raw input from the request
        raw_input = None
        if hasattr(request, "text"):
            raw_input = getattr(request, "text")
        elif hasattr(request, "raw_input"):
            raw_input = getattr(request, "raw_input")
        elif hasattr(request, "text"):
            raw_input = getattr(request, "text")

        # Initialize the pipeline context
        context = PipelineContext(
            request_id=getattr(request, "session_id", None) or getattr(request, "request_id", ""),
            transport=getattr(request, "transport", ""),
            raw_input=raw_input,
            metadata=dict(getattr(request, "metadata", {}) or {}),
        )

        # Return a stage result that continues the pipeline
        # with the initialized context
        return StageResult(
            outcome=StageOutcome.CONTINUE,
            context=context,
            metadata={
                "receive_status": "initialized",
                "request_id": context.request_id,
                "raw_input_length": len(raw_input) if raw_input else 0,
            },
        )