from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class ReceiveStage(PipelineStage):
    """Capture raw input and prepare the context for downstream stages."""

    @property
    def name(self) -> str:
        return "receive"

    async def execute(self, context: PipelineContext) -> StageResult:
        parsed: dict[str, object] = {
            "text": context.raw_input,
        }
        if context.attachments:
            parsed["attachment_count"] = len(context.attachments)
        context.parsed_request = parsed
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
