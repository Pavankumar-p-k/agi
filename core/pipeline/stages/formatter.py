from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class FormatterStage(PipelineStage):
    """Build the final response payload.

    This is the **last** stage in the pipeline.  It reads the outcome
    and epistemic tags and writes ``context.formatted_response``.
    No stage after Formatter should modify the response.
    """

    @property
    def name(self) -> str:
        return "formatter"

    async def execute(self, context: PipelineContext) -> StageResult:
        text = ""
        if context.outcome is not None:
            text = context.outcome.text
        elif context.execution_result:
            text = context.execution_result.get("text", "")
        if not text and context.error:
            text = f"Error: {context.error}"

        payload: dict[str, object] = {
            "text": text,
        }
        if context.epistemic_tags:
            payload["epistemic"] = dict(context.epistemic_tags)
        if context.metrics:
            payload["metrics"] = dict(context.metrics)

        context.formatted_response = payload
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
