from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class CapabilitySelectionStage(PipelineStage):
    """Match the classified intent to registered capabilities.

    Currently a pass-through that records the intent mode as a capability.
    When provider/capability registration matures, this stage will query
    ``core.agent_registry`` or the capability graph.
    """

    @property
    def name(self) -> str:
        return "capability_selection"

    async def execute(self, context: PipelineContext) -> StageResult:
        mode = "chat"
        if context.classification:
            mode = context.classification.get("mode", "chat")
        context.selected_capabilities = [f"intent:{mode}"]
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
