"""CapabilitySelectionStage — selects capabilities per plan step."""
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext


class CapabilitySelectionStage(PipelineStage):
    @property
    def name(self) -> str:
        return "capability_selection"

    async def execute(self, context: PipelineContext) -> StageResult:
        plan = context.plan
        steps = plan.get("steps", []) if isinstance(plan, dict) else []
        selection: dict = {}
        for i, step in enumerate(steps or []):
            intent = str((step or {}).get("intent", "respond"))
            if any(k in intent for k in ("research", "search")):
                selection[i] = [{"id": "research"}]
            elif any(k in intent for k in ("code", "build", "write")):
                selection[i] = [{"id": "coding"}]
            elif "documentation" in intent or "doc" in intent:
                selection[i] = [{"id": "documentation"}]
            else:
                selection[i] = [{"id": "chat"}]
        context.selected_capabilities = selection
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["CapabilitySelectionStage"]
