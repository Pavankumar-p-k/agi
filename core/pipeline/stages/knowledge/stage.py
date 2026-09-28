"""KnowledgeStage — Rule 50 owner of KnowledgeResult construction."""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.pipeline.knowledge_result import KnowledgeResult


class KnowledgeStage(PipelineStage):
    @property
    def name(self) -> str:
        return "knowledge"

    async def execute(self, context: PipelineContext) -> StageResult:
        services = getattr(context, "services", None)
        knowledge_id = services.uuid4() if services is not None \
            and hasattr(services, "uuid4") else ""
        entities: tuple = ()
        facts: tuple = ()
        # Extract simple entities/facts from the raw input (deterministic).
        raw = str(getattr(context, "raw_input", "") or "")
        words = tuple(w for w in dict.fromkeys(
            w.strip(".,!?\"'").lower() for w in raw.split()
        ) if len(w) > 3)[:10]
        entities = words
        facts = ()
        context.knowledge_result = KnowledgeResult(
            knowledge_id=knowledge_id,
            activity_id=getattr(context, "activity_id", "") or "",
            entities=entities,
            facts=facts,
            edges=(),
            node_count=len(entities) + len(facts),
            edge_count=0,
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


__all__ = ["KnowledgeStage"]
