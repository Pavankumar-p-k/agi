"""Memory stage — currently a pass-through.

Stores relevant context in the ``memory.memory_facade``.
Full implementation will persist conversation history, extracted
facts, and user preferences for future requests.
"""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class MemoryStage(PipelineStage):
    """Store execution context in the memory facade.

    **Invariant:** Only fires after Verification passes.
    """

    @property
    def name(self) -> str:
        return "memory"

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
