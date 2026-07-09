from __future__ import annotations

import logging
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class CapabilitySelectionStage(PipelineStage):
    @property
    def name(self) -> str:
        return "capability_selection"

    async def execute(self, context: PipelineContext) -> StageResult:
        plan = context.plan
        if plan is None:
            context.selected_capabilities = {}
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        steps = plan.get("steps", [])
        bindings: dict[int, list[Any]] = {}

        for i, step in enumerate(steps):
            intent = step.get("intent", "")
            capabilities = self._resolve(intent)
            if capabilities:
                bindings[i] = capabilities

        context.selected_capabilities = bindings
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    def _resolve(self, intent: str) -> list[Any]:
        from core.capability.registry import capability_registry

        return capability_registry.resolve_intent(intent)
