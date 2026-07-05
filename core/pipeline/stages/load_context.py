from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class LoadContextStage(PipelineStage):
    """Resolve user, session, and transport metadata.

    Populates ``context.metadata`` with any transport-level info that
    downstream stages may need (e.g. user preferences, channel type).
    Currently a pass-through — expand as transport adapters are built.
    """

    @property
    def name(self) -> str:
        return "load_context"

    async def execute(self, context: PipelineContext) -> StageResult:
        context.metadata.setdefault("transport", context.transport)
        if context.user_id:
            context.metadata.setdefault("user_id", context.user_id)
        if context.session_id:
            context.metadata.setdefault("session_id", context.session_id)
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
