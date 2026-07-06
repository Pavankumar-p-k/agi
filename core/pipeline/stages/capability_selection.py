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
        intent = intent.lower().strip()

        try:
            from core.capability.registry import capability_registry as _cr
            registry = _cr
        except Exception:
            registry = None

        from core.capability.models import Capability, _BUILTIN_CAPABILITIES

        intent_to_cap: dict[str, list[str]] = {
            "respond": ["documentation"],
            "search_web": ["research", "browser"],
            "browse_web": ["browser"],
            "write_code": ["coding"],
            "summarize": ["research", "documentation"],
            "research": ["research"],
            "analyze": ["research", "vision"],
            "translate": ["translation"],
            "generate_image": ["image_generation"],
            "send_email": ["email", "notifications"],
            "send_message": ["messaging", "notifications"],
            "run_command": ["terminal"],
            "deploy": ["deployment"],
            "test": ["testing"],
            "query_database": ["database"],
            "read_file": ["filesystem"],
            "write_file": ["filesystem"],
        }

        def _get_cap(cid: str) -> Capability | None:
            if registry is not None:
                try:
                    cap = registry.get(cid)
                    if cap is not None:
                        return cap
                except Exception:
                    pass
            return _BUILTIN_CAPABILITIES.get(cid)

        cap_ids = intent_to_cap.get(intent, [])
        results: list[Capability] = []
        for cid in cap_ids:
            cap = _get_cap(cid)
            if cap is not None:
                results.append(cap)

        if not results:
            fallback = _get_cap("documentation")
            if fallback is not None:
                results.append(fallback)

        return results
