"""ResourceAccessStage — grants access per resource scope (stub-light)."""
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext


class ResourceAccessStage(PipelineStage):
    @property
    def name(self) -> str:
        return "resource_access"

    async def execute(self, context: PipelineContext) -> StageResult:
        class _Access:
            granted = True
            reason = "default allow"
        context.resource_access_result = _Access()
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["ResourceAccessStage"]
